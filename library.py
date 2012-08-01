#!/usr/bin/python

# Copyright (C) 2010-2012 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Extended function library for request handlers for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import datetime
import json
import logging
import re

# Third-party libraries
from icalendar import Calendar

# App engine specific libraries
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.ext import ndb
from google.appengine import runtime

# App specific libraries
from custom_exceptions import BadInterval
from handler_utils import DeferFunctionDecorator
from handler_utils import EmailAdmins
from models import Event
import time_utils


CALENDAR_ID = 'vhoam1gb7uqqoqevu91liidi80@group.calendar.google.com'
RESPONSES = {1: ['once a week', 'week'],
             4: ['every two days', 'two-day'],
             7: ['once a day', 'day'],
             14: ['twice a day', 'half-day'],
             28: ['every six hours', 'six-hrs'],
             56: ['every three hours', 'three-hrs']}


def UpdateString(update_intervals):
  """Calculates a short and long message to represent frequency of updates.

  Args:
    update_intervals: A list of interval numbers (between 0 and 55) that
        represent the times an update will occur

  Returns:
    A two-tuple of the long and short message (respectively) corresponding to
        the frequency. This is intended to be sent via AJAX and hence the
        tuple is turned into json before being returned.

  Raises:
    BadInterval in the case that the length of update_intervals is not
        a key in the constant RESPONSES
  """
  length = len(update_intervals)
  if length not in RESPONSES:
    raise BadInterval(length)
  else:
    return json.dumps(RESPONSES[length])


def WhiteList(link):
  """Determines if a link is on the whitelist and transforms it if needed.

  Args:
    link: A url corresponding to a calendar feed

  Returns:
    A tuple (valid, transformed) where valid is a boolean which indicates
        whether the link is on the whitelist and transformed is an
        (possibly different) equivalent value of link which is used
        internally.
  """
  # If WhiteList is updated, event parsing must be as well
  valid = False
  transformed = link

  pattern_tripit = ('^(?P<protocol>(http|https|webcal)://|)www.tripit.com/feed/'
                    'ical/private/[A-Za-z0-9-]+/tripit.ics$')
  tripit_match = re.match(pattern_tripit, link)
  if tripit_match is not None:
    valid = True

    protocol = tripit_match.group('protocol')
    transformed = 'http://{}'.format(link[len(protocol):])

  return valid, transformed


@DeferFunctionDecorator
def MonthlyCleanup(relative_date):
  """Deletes events older than three months.

  Will delete events from the datastore that are older than three months. First
  checks that the date provided is at most two days prior to the current one.

  NOTE: This would seem to argue that relative_date should not be provided, but
  we want to use the relative_date from the server that is executing the cron
  job, not the one executing the cleanup (as there may be some small
  differences). In the case that relative_date does not pass this check, we log
  and send and email to the admins, but do not raise an error. This is done so
  this can be removed from the task queue in the case of the invalid input.

  Args:
    relative_date: date provided by calling script. Expected to be current date.
  """
  prior_date_day = relative_date.day

  prior_date_month = relative_date.month - 3
  if prior_date_month < 1:
    prior_date_year = relative_date.year - 1
    prior_date_month += 12
  else:
    prior_date_year = relative_date.year

  prior_date = datetime.date(year=prior_date_year,
                             month=prior_date_month,
                             day=prior_date_day)

  today = datetime.date.today()
  if today - relative_date > datetime.timedelta(days=2):
    msg = ('MonthlyCleanup called with bad date {relative_date} '
           'on {today}.'.format(relative_date=relative_date, today=today))
    logging.info(msg)
    EmailAdmins(msg, defer_now=True)  # pylint:disable-msg=E1123
    return

  prior_date_as_str = time_utils.FormatTime(prior_date)
  old_events = Event.query(Event.end_date <= prior_date_as_str)
  for event in old_events:
    event.delete()


@DeferFunctionDecorator
def UpdateUpcoming(user_cal, upcoming, credentials=None):
  """Updates the GCal inst. by deleting events removed from extern. calendar.

  If the new upcoming events list is different from that on the user_cal, it
  will iterate through the difference and address events that no longer belong.
  Such events would have been previously marked as upcoming (and stored in
  UserCal.upcoming) and would not have occurred by the time UpdateUpcoming was
  called. For such events, the user will be removed from the list of attendees.
  If there are other remaining users, the event will be updated, else it will be
  deleted from both the datastore and GCal.

  Args:
    user_cal: a UserCal object that will have upcoming events updated
    upcoming: a list of UID strings representing events in the subscribed feeds
        of the user that have not occurred yet (i.e. they are upcoming)
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is the default value of None, future
        methods will attempt to get credentials from the default credentials.
  """
  logging.info('UpdateUpcoming called with: {!r}'.format(locals()))

  upcoming.sort()
  if user_cal.upcoming != upcoming:
    now = datetime.datetime.utcnow()
    for uid in user_cal.upcoming:
      if uid not in upcoming:
        event = ndb.Key(Event, uid).get()
        if event.end.to_datetime() > now:  # pylint:disable-msg=E1103
          # If federated identity not set, User.__cmp__ only uses email
          event.attendees.remove(user_cal.owner)  # pylint:disable-msg=E1103
          if not event.attendees:  # pylint:disable-msg=E1103
            event.delete(credentials=credentials)  # pylint:disable-msg=E1103
          else:
            event.update(credentials=credentials)  # pylint:disable-msg=E1103

    user_cal.upcoming = upcoming
    user_cal.put()


# pylint:disable-msg=R0913
@DeferFunctionDecorator
def UpdateUserSubscriptions(user_cal, credentials=None, links=None,
                            link_index=0, upcoming=None, last_used_uid=None):
  """Updates a list of calendar subscriptions for a user.

  Loops through each subscription URL in links (or user_cal.calendars) and calls
  UpdateSubscription for each URL. Keeps a list of upcoming events which will
  be updated by UpdateUpcoming upon completion. If the application encounters
  one of the two DeadlineExceededError's while the events are being processed,
  the function calls itself, but uses the upcoming, link_index and
  last_used_uid keyword arguments to save the current processing state.

  Args:
    user_cal: a UserCal object that will have upcoming subscriptions updated
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is the default value of None, future
        methods will attempt to get credentials from the default credentials.
    links: a list of URLs to the .ics subscription feeds. This is None by
        default, in which case user_cal.calendars is used.
    link_index: a placeholder index within the list of links which is 0 by
        default. This is intended to be passed in only by calls from
        UpdateUserSubscriptions.
    upcoming: a list of UID strings representing events in the subscribed feeds
        of the user that have not occurred yet (i.e. they are upcoming). By
        default this value is None and transformed to [] within the function.
    last_used_uid: a placeholder UID which is None by default. This is intended
        to be passed in only by calls from UpdateUserSubscriptions. In the case
        it is not None, it will serve as a starting index within the set of UIDs
        from the first subscription (first element of links) that is updated.
  """
  if links is None:
    links = user_cal.calendars

  if link_index > 0:
    links = links[link_index:]
  upcoming = upcoming or []

  # Set default values for link index and last used uid variables. These
  # are used to to pick up where the loop left off in case the task encounters
  # one of the DeadlineExceededError's.
  index = 0
  uid = None

  try:
    for index, link in enumerate(links):
      # In the case last_used_uid is not None, we may be picking up in the
      # middle of the feed for the first link in {links}
      if index == 0 and last_used_uid is not None:
        uid_generator = UpdateSubscription(link, user_cal.owner,
                                           credentials=credentials,
                                           start_uid=last_used_uid)
      else:
        uid_generator = UpdateSubscription(link, user_cal.owner,
                                           credentials=credentials)

      for uid, is_upcoming, failed in uid_generator:
        if is_upcoming:
          upcoming.append(uid)
        elif failed:
          msg = 'silently failed operation on {uid} from {link}'.format(
              uid=uid, link=link)
          logging.info(msg)
          EmailAdmins(msg, defer_now=True)  # pylint:disable-msg=E1123
  except (runtime.DeadlineExceededError, urlfetch_errors.DeadlineExceededError):
    # NOTE: upcoming has possibly been updated inside the try statement
    # pylint:disable-msg=E1123
    UpdateUserSubscriptions(user_cal, credentials=credentials, links=links,
                            link_index=index, upcoming=upcoming,
                            last_used_uid=uid, defer_now=True)
    return

  # If the loop completes without timing out
  # pylint:disable-msg=E1123
  UpdateUpcoming(user_cal, upcoming, credentials=credentials, defer_now=True)


def UpdateSubscription(link, current_user, credentials=None, start_uid=None):
  """Updates the GCal instance with the events in link for the current_user.

  Args:
    link: Link to calendar feed being subscribed to
    current_user: a User instance corresponding to the user that is updating
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is the default value of None, future
        methods will attempt to get credentials from the default credentials.
    start_uid: a placeholder UID which is None by default. This is intended
        to be passed in only by calls from UpdateUserSubscriptions. In the case
        it is not None, it will serve as a starting index within the set of
        event UIDs from {link}.

  Returns:
    A generator instance which yields tuples (uid, is_upcoming, failed) tuples
        where uid is the id of an event, is_upcoming is a boolean that is True
        if and only if the event has not occurred yet (i.e. is upcoming) and
        failed is a boolean that is True if and only if the three attempts to
        add or update the event fail.
  """
  logging.info('UpdateSubscription called with: {!r}'.format(locals()))

  valid, link = WhiteList(link)
  if not valid:
    # Do nothing if not on the whitelist
    # http://www.python.org/dev/peps/pep-0255/ (Specification: Return)
    return

  now = datetime.datetime.utcnow()

  import_feed = urlfetch.fetch(link, deadline=60)
  ical = Calendar.from_ical(import_feed.content)

  start_index = 0
  if start_uid is not None:
    # pylint:disable-msg=E1103
    uid_list = [component.get('uid', '') for component in ical.walk()]
    if start_uid in uid_list:
      start_index = uid_list.index(start_uid)

  for component in ical.walk()[start_index:]:  # pylint:disable-msg=E1103
    if component.name != 'VEVENT':
      msg = ('iCal at {link} has unexpected event type '
             '{component.name}'.format(link=link, component=component))
      logging.info(msg)
      if component.name != 'VCALENDAR':
        EmailAdmins(msg, defer_now=True)  # pylint:disable-msg=E1123
    else:
      event, failed = Event.from_ical_event(component, current_user,
                                            credentials=credentials)

      uid = event.key.id()
      if failed:
        yield (uid, False, True)
      else:
        is_upcoming = event.end.to_datetime() > now
        yield (uid, is_upcoming, False)

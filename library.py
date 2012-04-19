#!/usr/bin/python

# Copyright (C) 2010-2011 Google Inc.
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
import logging
import os
import re
import simplejson
import sys
from time import sleep
import traceback
from urllib2 import urlopen

# Third-party libraries
from apiclient.discovery import build_from_document
from apiclient.discovery import DISCOVERY_URI
from apiclient.errors import HttpError
import httplib2
from icalendar import Calendar
from oauth2client.file import Storage
import uritemplate

# App engine specific libraries
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.ext import db
from google.appengine.ext.deferred import defer
from google.appengine.ext.deferred import PermanentTaskFailure
from google.appengine.ext.webapp import RequestHandler
from google.appengine.ext.webapp import template
from google.appengine import runtime


# App specific libraries
from admins import ADMINS_TO
from models import Event
from secret_key import CLIENT_ID
from secret_key import CLIENT_SECRET
from secret_key import DEVELOPER_KEY


CALENDAR_ID = 'vhoam1gb7uqqoqevu91liidi80@group.calendar.google.com'
CREDENTIALS_FILENAME = 'calendar.dat'
RESPONSES = {1: ['once a week', 'week'],
             4: ['every two days', 'two-day'],
             7: ['once a day', 'day'],
             14: ['twice a day', 'half-day'],
             28: ['every six hours', 'six-hrs'],
             56: ['every three hours', 'three-hrs']}
PATH_TO_500_TEMPLATE = os.path.join(os.path.dirname(__file__),
                                    'templates', '500.html')
RENDERED_500_PAGE = template.render(PATH_TO_500_TEMPLATE, {})
DISCOVERY_DOC_FILENAME = 'calendar_discovery.json'
DISCOVERY_DOC_PARAMS = {'api': 'calendar', 'apiVersion': 'v3'}
FUTURE_LOCATION = ('http://code.google.com/p/google-api-python-client/source/'
                   'browse/apiclient/contrib/calendar/future.json')


# Global Setting
urlfetch.set_default_fetch_deadline(60)


class Error(Exception):
  """Base error class for library functions."""


class BadInterval(Error):
  """Error corresponding to an unanticipated number of update intervals."""


class UnexpectedDescription(Error):
  """Error corresponding to an unexpected event description."""


class CredentialsLoadError(Error):
  """Error when credentials are not loaded correctly from a specified file."""


def JsonAscii(obj):
  """Calls simplejson.dumps with ensure_ascii explicitly set to True.

  Args:
    obj: any object that can be turned into json

  Returns:
    A JSON representation of obj that is guaranteed to contain only
        ascii characters (this is because we use it to store certain
        objects in mdoels.Event.event_data as a TextProperty)
  """
  return simplejson.dumps(obj, ensure_ascii=True)


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
    return simplejson.dumps(RESPONSES[length])


def InitCredentials(filename=CREDENTIALS_FILENAME):
  """Initializes an OAuth2Credentials object from a file.

  Args:
    filename: The location of the pickled contents of the
        OAuth2Credentials object.

  Returns:
    An OAuth2Credentials object.
  """
  storage = Storage(CREDENTIALS_FILENAME)
  credentials = storage.get()

  if credentials is None or credentials.invalid == True:
    email_admins('Credentials in calendar resource not good.', defer_now=True)
    raise CredentialsLoadError('No credentials retrieved from calendar.dat')

  return credentials


def InitService(credentials=None):
  """Initializes a service object to make calendar requests.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials from
        calendar.dat file.

  Returns:
    A Resource object intended for making calls to an Apiary API.

  Raises:
    CredentialsLoadError in the case that no credentials are passed in and they
        can't be loaded from the specified file
  """
  if credentials is None:
    credentials = InitCredentials()

  http = httplib2.Http()
  http = credentials.authorize(http)

  # Can use with statement once on 2.7
  fh = open(DISCOVERY_DOC_FILENAME, 'rU')
  cached_discovery_doc = fh.read()
  fh.close()

  return build_from_document(cached_discovery_doc,
                             DISCOVERY_URI,
                             http=http,
                             developerKey=DEVELOPER_KEY)


def ConvertToInterval(timestamp):
  """Converts a datetime timestamp to a time interval for a cron job.

  Args:
    timestamp: a datetime.datetime object

  Returns:
    A value between 0 and 55 corresponding to the interval the timestamp
    falls in. In this calculation, 12am on Monday is interval 0 and each
    interval lasts 3 hours.
  """
  # In datetime, Monday is day 0, sunday is day 6
  # Since 8 intervals in a day, multiply by 8. Round up hours.
  interval = 8*timestamp.weekday() + timestamp.hour/3 + 1

  # If we are exactly on an hour that is a multiple of three
  # we do not wish to round up since floor(x) == ceil(x), contrary
  # to all other cases where ceil(x) == floor(x) + 1
  relative_seconds = sum([3600*(timestamp.hour % 3 == 0),
                          60*timestamp.minute,
                          timestamp.second,
                          timestamp.microsecond/1000.0])
  if relative_seconds < 300:  # under 5 minutes past schedule
    interval -= 1

  return interval % 56


def FormatTime(time_value):
  """Takes a datetime object and returns a formatted time stamp.

  Args:
    time_value: a datetime.datetime or datetime.date object

  Returns:
    A string value of the datetime object formatted according to the values
        set in time_parse below
  """
  # Fails if not datetime.datetime or datetime.datetime

  # strftime('%Y-%m-%dT%H:%M:%S.000Z') for datetime
  # strftime('%Y-%m-%d') for date

  # Default TZ is UTC/GMT (as is TZ in GCal)
  time_parse = '%Y-%m-%d'
  if isinstance(time_value, datetime.datetime):
    time_parse += 'T%H:%M:%S.000Z'
    return time_value.strftime(time_parse)
  elif isinstance(time_value, datetime.date):
    return time_value.strftime(time_parse)


def TimeToDTStamp(time_as_str):
  """Takes time as string and returns a datetime object.

  NOTE: Default timezone is UTC/GMT

  Args:
    time_as_str: a string version of a timestamp which must be in one of
        two formats '%Y-%m-%dT%H:%M:%S.000Z' or '%Y-%m-%d' which correspond
        to datetime.datetime and datetime.date respectively

  Returns:
    A datetime.datetime or datetime.date object if {time_as_str} fits one of the
        formats else None
  """
  time_parse = '%Y-%m-%d'
  try:
    converted_val = datetime.datetime.strptime(time_as_str, time_parse)
    return converted_val
  except ValueError:
    pass

  time_parse += 'T%H:%M:%S.000Z'
  try:
    converted_val = datetime.datetime.strptime(time_as_str, time_parse)
    return converted_val
  except ValueError:
    pass


def StringToDayString(time_as_str):
  """Takes time as string (date or datetime) and returns date as string.

  Args:
    time_as_str: a string version of a timestamp which must be in one of
        two formats '%Y-%m-%dT%H:%M:%S.000Z' or '%Y-%m-%d' which correspond
        to datetime.datetime and datetime.date respectively

  Returns:
    A string value corresponding to the date only in the format '%Y-%m-%d'
  """
  datetime_obj = TimeToDTStamp(time_as_str)
  if datetime_obj is not None:
    if isinstance(datetime_obj, datetime.datetime):
      datetime_obj = datetime_obj.date()
    return datetime_obj.strftime('%Y-%m-%d')


def RemoveTimezone(time_value):
  """Takes a datetime object and removes the timezone.

  NOTE: This is done to allow comparison of all acceptable timestamps.
  In the case that time_value is not an expected type, we simply
  return the original time_value and let the caller deal with the
  unexpected return type.

  Args:
    time_value: a datetime.datetime or datetime.date object

  Returns:
    If time_value is a datetime.datetime object, a new datetime.datetime
        object is returned with the same values but with time zone stripped,
        else if time_value is a datetime.date object a datetime.datetime
        object at 12am on the same date as time_value is returned (again
        with no time zone), else the original value of time_value is
        returned.
  """
  if isinstance(time_value, datetime.datetime):
    if time_value.tzinfo is not None:
      time_parse = '%Y-%m-%dT%H:%M:%S.000Z'
      time_value = time_value.strftime(time_parse)  # TZ is lost
      time_value = datetime.datetime.strptime(time_value, time_parse)
  elif isinstance(time_value, datetime.date):
    # convert to datetime.datetime object for comparison
    time_value = datetime.datetime(year=time_value.year,
                                   month=time_value.month,
                                   day=time_value.day)

  return time_value


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
  # If we WhiteList is updated, ParseEvent must be as well
  valid = False
  transformed = link

  pattern_webcal = ('^webcal://www.tripit.com/feed/ical/private/'
                    '[A-Za-z0-9-]+/tripit.ics$')
  pattern_http = ('^http://www.tripit.com/feed/ical/private/'
                  '[A-Za-z0-9-]+/tripit.ics$')
  if re.match(pattern_webcal, link):
    valid = True

    len_webcal = len('webcal')
    transformed = 'http%s' % link[len_webcal:]
  elif re.match(pattern_http, link):
    valid = True
    transformed = link

  return valid, transformed


def AddOrUpdateEvent(event_data, credentials, email=None,
                     event=None, push_update=True):
  """Create event in main application calendar and add user as attendee.

  Args:
    event_data: a dictionary containing data relevant to a specific event
    credentials: An OAuth2Credentials object used to build a service object.
    email: an optional email address that is used in the case that the event
        already exists and we are adding a new attendee via their email address
    event: a dictionary of data to be sent with a Resource object. When None,
        corresponds to a new event.
    push_update: an optional boolean which defaults to True. When set to True,
        This will force updates on the existing event (if event is not None)

  Returns:
    A dictionary containing the contents of the event that was added or updated.
        If update or insert request times out after three tries, returns None.
  """
  service = InitService(credentials)

  update = True
  if event is None:
    event = {}
    update = False

  event['summary'] = event_data['summary']
  event['description'] = event_data['description']

  # Where
  event['location'] = event_data['location']

  # When
  start = event_data['when:from']
  if start.endswith('Z'):
    event['start'] = {'dateTime': start}
  else:
    event['start'] = {'date': start}

  end = event_data['when:to']
  if end.endswith('Z'):
    event['end'] = {'dateTime': end}
  else:
    event['end'] = {'date': end}

  if update:
    attempts = 3
    updated_event = None
    if push_update:
      while attempts:
        try:
          updated_event = service.events().update(calendarId=CALENDAR_ID,
                                                  eventId=event['id'],
                                                  body=event).execute()
          logging.info('%s updated', updated_event['id'])
          break
        except HttpError, e:
          logging.info(e)
          attempts -= 1
          sleep(3)

    return updated_event
  else:
    # Who
    if 'attendees' not in event:
      event['attendees'] = []
    event['attendees'].append({'email': email})

    attempts = 3
    new_event = None
    while attempts:
      try:
        new_event = service.events().insert(calendarId=CALENDAR_ID,
                                            body=event).execute()
        logging.info('%s was inserted', new_event['id'])
        break
      except HttpError, e:
        logging.info(e)
        attempts -= 1
        sleep(3)

    return new_event


def ParseEvent(event):
  """Parses an iCalendar.cal.Event instance to a predefined format.

  In the whitelisted feeds, all events have a UID. Almost all events begin
  with 'item-'. Those that don't begin with 'item-' are a placeholder event
  event for the entire length of the trip. In this case, we expect the
  description to resemble the phrase '{name} is in {location}'. This holds
  except in the case that the location is 'No destination specified', in
  which case description resembles '{name} is in an unspecified location'. Since
  events may be attended by multiple users, we replace '{name} is in' with
  the phrase 'In'.

  Args:
    event: an icalendar.cal.Event object parsed from a .ics feed.

  Returns:
    A tuple (uid, event_data) where uid is an attribute from the event
        and event_data is a dictionary containing the start and end times
        of the event, and the summary, location and description of the event.

  Raises:
    UnexpectedDescription in the case that the description does not contain the
        phrase we expect it to.
  """
  uid = unicode(event.get('uid'))
  description = unicode(event.get('description'))
  location = unicode(event.get('location'))

  # The phrase 'No destination specified' does not match its
  # counterpart in the description, so we transform {location}.
  if location == 'No destination specified':
    location = 'an unspecified location'

  # Check description is formed as we expect
  if not uid.startswith('item-'):
    target = ' is in %s ' % location
    if description.count(target) != 1:
      raise UnexpectedDescription(description)

    # remove name from the description
    description = 'In %s %s' % (location, description.split(target)[1])

  event_data = {'when:from': FormatTime(event.get('dtstart').dt),
                'when:to': FormatTime(event.get('dtend').dt),
                'summary': unicode(event.get('summary')),
                'location': location,
                'description': description}
  return uid, event_data


def RetrieveCalendarDiscoveryDoc(credentials=None):
  if credentials is None:
    credentials = InitCredentials()

  http = httplib2.Http()
  http = credentials.authorize(http)

  requested_url = uritemplate.expand(DISCOVERY_URI, DISCOVERY_DOC_PARAMS)
  resp, content = http.request(requested_url)

  success = False
  if resp.status < 400:
    try:
      service = simplejson.loads(content)
      success = True
    except ValueError:
      pass

  return success, content


def CheckCalendarDiscoveryDoc(credentials=None):
  success, current_discovery_doc = RetrieveCalendarDiscoveryDoc(
      credentials=credentials)

  if not success:
    email_admins('Couldn\'t retrieve discovery doc.', defer_now=True)
    return

  # Can use with statement once on 2.7
  fh = open(DISCOVERY_DOC_FILENAME, 'rU')
  cached_discovery_doc = fh.read()
  fh.close()

  if cached_discovery_doc != current_discovery_doc:
    email_admins('Current discovery doc disagrees with cached version.',
                 defer_now=True)


def CheckFutureFeaturesDoc(future_location=FUTURE_LOCATION):
  http = httplib2.Http()
  resp, _ = http.request(future_location)

  if resp.status != 404:
    email_admins('Future features JSON responded with %s.' % resp.status,
                 defer_now=True)


def MonthlyCleanup(relative_date, defer_now=False):
  """Deletes events older than three months.

  Will delete events from the datastore that are older than three months. First
  checks that the date provided is at most two days prior to the current one.

  NOTE: This would seem to argue that relative_date should not be provided, but
  we want to use the relative_date from the server that is executing the cron
  job, not the one executing the cleanup (as there may be some small
  differences). In the that relative_date does not pass this check, we log and
  send and email to the admins, but do not raise an error. This is done so
  this can be removed from the task queue in the case of the invalid input.

  Args:
    relative_date: date provided by calling script. Expected to be current date.
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('%s called with: %s', 'MonthlyCleanup', locals())

  if defer_now:
    defer(MonthlyCleanup, relative_date, defer_now=False, _url='/workers')
    return

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
    msg = 'MonthlyCleanup called with bad date %s on %s.' % (relative_date,
                                                             today)
    logging.info(msg)
    email_admins(msg, defer_now=True)
    return

  prior_date_as_str = FormatTime(prior_date)
  old_events = Event.gql('WHERE end_date <= :date', date=prior_date_as_str)
  for event in old_events:
    logging.info('%s removed from datastore. %s remains in calendar.',
                 event, event.gcal_edit)
    event.delete()


def UpdateUpcoming(user_cal, upcoming, credentials):
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
  """
  logging.info('%s called with: %s', 'UpdateUpcoming', locals())

  service = InitService(credentials)

  # TODO(dhermes) Calling set() everytime is expensive. Update UserCal to
  #               ensure UserCal.upcoming is a sorted list of unique elements.
  if set(user_cal.upcoming) != set(upcoming):
    now = datetime.datetime.utcnow()
    for uid in set(user_cal.upcoming).difference(upcoming):
      event = Event.get_by_key_name(uid)
      # pylint:disable-msg=E1103
      event_data = simplejson.loads(event.event_data)
      if TimeToDTStamp(event_data['when:to']) > now:
        event.who.remove(user_cal.owner.user_id())  # pylint:disable-msg=E1103
        if not event.who:  # pylint:disable-msg=E1103
          # pylint:disable-msg=E1103
          service.events().delete(calendarId=CALENDAR_ID,
                                  eventId=event.gcal_edit).execute()
          # pylint:disable-msg=E1103
          logging.info('%s deleted', event.gcal_edit)
          event.delete()  # pylint:disable-msg=E1103
        else:
          # TODO(dhermes) To avoid two trips to the server, reconstruct
          #               the CalendarEventEntry from the data in event
          #               rather than using GET
          # pylint:disable-msg=E1103
          cal_event = service.events().get(calendarId=CALENDAR_ID,
                                           eventId=event.gcal_edit).execute()
          # Filter out this user from the event attendees
          # pylint:disable-msg=E1103
          if 'attendees' not in cal_event:
            cal_event['attendees'] = []
          cal_event['attendees'] = [
              attendee_dict for attendee_dict in cal_event['attendees']
              if attendee_dict['email'] != user_cal.owner.email()
          ]

          service.events().update(calendarId=CALENDAR_ID,
                                  eventId=cal_event['id'],
                                  body=cal_event).execute()
          event.put()

    user_cal.upcoming = list(set(upcoming))
    user_cal.put()


def UpdateUserSubscriptions(links, user_cal, credentials, upcoming=None,
                            link_index=0, last_used_uid=None, defer_now=False):
  """Updates a list of calendar subscriptions for a user.

  Loops through each subscription URL in links and calls UpdateSubscription for
  each URL. Keeps a list of upcoming events which will be updated by
  UpdateUpcoming upon completion. If the application encounters one of the two
  DeadlineExceededError's while the events are being processed, the function
  calls itself, but uses the upcoming, link_index and last_used_uid keyword
  arguments to save the current processing state.

  Args:
    links: a list of URLs to the .ics subscription feeds
    user_cal: a UserCal object that will have upcoming subscriptions updated
    credentials: An OAuth2Credentials object used to build a service object.
    upcoming: a list of UID strings representing events in the subscribed feeds
        of the user that have not occurred yet (i.e. they are upcoming). By
        default this value is None and transformed to [] within the function.
    link_index: a placeholder index within the list of links which is 0 by
        default. This is intended to be passed in only by calls from
        UpdateUserSubscriptions.
    last_used_uid: a placeholder UID which is None by default. This is intended
        to be passed in only by calls from UpdateUserSubscriptions. In the case
        it is not None, it will serve as a starting index within the set of UIDs
        from the first subscription (first element of links) that is updated.
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('%s called with: %s', 'UpdateUserSubscriptions', locals())

  if defer_now:
    defer(UpdateUserSubscriptions, links, user_cal, credentials,
          upcoming=upcoming, link_index=link_index,
          last_used_uid=last_used_uid, defer_now=False, _url='/workers')
    return

  service = InitService(credentials)

  if link_index > 0:
    links = links[link_index:]
  upcoming = [] if upcoming is None else upcoming

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
                                           credentials, start_uid=last_used_uid)
      else:
        uid_generator = UpdateSubscription(link, user_cal.owner, credentials)

      for uid, is_upcoming, failed in uid_generator:
        if is_upcoming:
          upcoming.append(uid)
        elif failed:
          logging.info('silently failed operation on %s from %s', uid, link)
          email_admins('silently failed operation on %s from %s' % (uid, link),
                       defer_now=True)
  except (runtime.DeadlineExceededError, urlfetch_errors.DeadlineExceededError):
    # NOTE: upcoming has possibly been updated inside the try statement
    defer(UpdateUserSubscriptions, links, user_cal, credentials,
          upcoming=upcoming, link_index=index, last_used_uid=uid,
          defer_now=defer_now, _url='/workers')
    return

  # If the loop completes without timing out
  defer(UpdateUpcoming, user_cal, upcoming, credentials, _url='/workers')
  return


def UpdateSubscription(link, current_user, credentials, start_uid=None):
  """Updates the GCal instance with the events in link for the current_user.

  Args:
    link: Link to calendar feed being subscribed to
    current_user: a User instance corresponding to the user that is updating
    credentials: An OAuth2Credentials object used to build a service object.
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
  logging.info('%s called with: %s', 'UpdateSubscription', locals())

  service = InitService(credentials)

  valid, link = WhiteList(link)
  if not valid:
    # Do nothing if not on the whitelist
    # http://www.python.org/dev/peps/pep-0255/ (Specification: Return)
    return

  current_user_id = current_user.user_id()
  now = datetime.datetime.utcnow()

  import_feed = urlopen(link)
  ical = Calendar.from_string(import_feed.read())
  import_feed.close()

  start_index = 0
  if start_uid is not None:
    # pylint:disable-msg=E1103
    uid_list = [component.get('uid', '') for component in ical.walk()]
    if start_uid in uid_list:
      start_index = uid_list.index(start_uid)

  for component in ical.walk()[start_index:]:  # pylint:disable-msg=E1103
    if component.name != 'VEVENT':
      msg = 'iCal at %s has unexpected event type %s' % (link, component.name)
      logging.info(msg)
      if component.name != 'VCALENDAR':
        email_admins(msg, defer_now=True)
    else:
      uid, event_data = ParseEvent(component)
      event = Event.get_by_key_name(uid)
      if event is None:
        # Create new event
        # (leaving out the event argument creates a new event)
        cal_event = AddOrUpdateEvent(event_data, credentials,
                                     email=current_user.email())
        # TODO(dhermes) add to failed queue to be updated by a cron
        if cal_event is None:
          yield (uid, False, True)
          continue

        gcal_edit = cal_event['id']
        end_date = StringToDayString(event_data['when:to'])
        event = Event(key_name=uid,
                      who=[current_user_id],  # id is string
                      event_data=db.Text(JsonAscii(event_data)),
                      end_date=end_date,
                      gcal_edit=gcal_edit)
        event.put()

        # execution has successfully completed
        # TODO(dhermes) catch error on get call below
        yield (uid, RemoveTimezone(component.get('dtend').dt) > now, False)
      else:
        # We need to make changes for new event data or a new owner
        if (current_user_id not in event.who or
            db.Text(JsonAscii(event_data)) != event.event_data):
          # Grab GCal event to edit
          attempts = 3
          cal_event = None
          while attempts:
            try:
              # pylint:disable-msg=E1103
              cal_event = service.events().get(
                  calendarId=CALENDAR_ID, eventId=event.gcal_edit).execute()
              # pylint:disable-msg=E1103
              logging.info('GET sent to %s', event.gcal_edit)
              break
            except HttpError, e:
              logging.info(e)
              attempts -= 1
              sleep(3)

          # TODO(dhermes) add to failed queue to be updated by a cron
          if cal_event is None:
            yield (uid, False, True)
            continue

          # Update who
          if current_user_id not in event.who:  # pylint:disable-msg=E1103
            # pylint:disable-msg=E1103
            event.who.append(current_user_id)  # id is string

            # add existing event to current_user's calendar
            if 'attendees' not in cal_event:
              cal_event['attendees'] = []
            cal_event['attendees'].append({'email': current_user.email()})

          # Update existing event
          # pylint:disable-msg=E1103
          if db.Text(JsonAscii(event_data)) != event.event_data:
            event.event_data = db.Text(JsonAscii(event_data))

            # Don't push update to avoid pushing twice (if both changed)
            AddOrUpdateEvent(event_data,
                             credentials,
                             event=cal_event,
                             push_update=False)
            # push_update=False, impossible to have HttpError

          # Push all updates to calendar event
          attempts = 3
          while attempts:
            try:
              service.events().update(calendarId=CALENDAR_ID,
                                      eventId=cal_event['id'],
                                      body=cal_event).execute()
              logging.info('%s updated', cal_event['id'])

              # After all possible changes to the Event instance have occurred
              event.put()  # pylint:disable-msg=E1103
              break
            except HttpError, e:
              logging.info(e)
              attempts -= 1
              sleep(3)

          # If attempts is 0, we have failed and don't want to add the
          # uid to results
          if attempts == 0:
            yield (uid, False, True)
            continue

        # execution has successfully completed
        # TODO(dhermes) catch error on get call below
        yield (uid, RemoveTimezone(component.get('dtend').dt) > now, False)

################################################
############# Handler class helper #############
################################################

def email_admins(error_msg, defer_now=False):
  """Sends email to admins with the preferred message, with option to defer.

  Uses the template error_notify.templ to generate an email with the {error_msg}
  sent to the list of admins in admins.ADMINS_TO.

  Args:
    error_msg: A string containing an error to be sent to admins by email
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  if defer_now:
    defer(email_admins, error_msg, defer_now=False, _url='/workers')
    return

  sender = 'Persistent Cal Errors <errors@persistent-cal.appspotmail.com>'
  subject = 'Persistent Cal Error: Admin Notify'
  email_path = os.path.join(os.path.dirname(__file__),
                            'templates', 'error_notify.templ')
  body = template.render(email_path, {'error': error_msg})
  mail.send_mail(sender=sender, to=ADMINS_TO,
                 subject=subject, body=body)


def deadline_decorator(method):
  """Decorator for HTTP verbs to handle GAE timeout.

  Args:
    method: a callable object, expected to be a method of an object from
        a class that inherits from RequestHandler

  Returns:
    A new function which calls {method}, catches certain errors
        and responds to them gracefully
  """

  def wrapped_method(self, *args, **kwargs):
    """Returned function that uses method from outside scope.

    Tries to execute the method with the arguments. If either a
    PermanentTaskFailure is thrown (from deferred library) or if one of the two
    DeadlineExceededError's is thrown (inherits directly from BaseException)
    administrators are emailed and then cleanup occurs.
    """
    try:
      method(self, *args, **kwargs)
    except PermanentTaskFailure:
      # In this case, the function can't be run, so we alert but do not
      # raise the error, returning a 200 status code, hence killing the task.
      msg = 'Permanent failure attempting to execute task.'
      logging.exception(msg)
      email_admins(msg, defer_now=True)
    except (runtime.DeadlineExceededError,
            urlfetch_errors.DeadlineExceededError):
      traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
      logging.exception(traceback_info)
      email_admins(traceback_info, defer_now=True)

      self.response.clear()
      self.response.set_status(500)
      self.response.out.write(RENDERED_500_PAGE)

  return wrapped_method


class ExtendedHandler(RequestHandler):
  """A custom version of GAE RequestHandler.

  This subclass of RequestHandler defines a handle_exception
  function that will email administrators when an exception
  occurs. In addition, the __new__ method is overridden
  to allow custom wrappers to be placed around the HTTP verbs
  before an instance is created.
  """

  def __new__(cls, *args, **kwargs):
    """Constructs the object.

    This is explicitly intended for Google App Engine's RequestHandler.
    Requests only suport 7 of the 9 HTTP verbs, 4 of which we will
    decorate: get, post, put and delete. The other three supported
    (head, options, trace) may be added at a later time.
    Args:
      cls: A reference to the class

    Reference: ('http://code.google.com/appengine/docs/python/tools/'
                'webapp/requesthandlerclass.html')
    """
    verbs = ['get', 'post', 'put', 'delete']

    for verb in verbs:
      method = getattr(cls, verb, None)
      if callable(method):
        setattr(cls, verb, deadline_decorator(method))

    return super(ExtendedHandler, cls).__new__(cls, *args, **kwargs)

  def handle_exception(self, exception, debug_mode):
    """Custom handler for all GAE errors that inherit from Exception.

    Args:
      exception: the exception that was thrown
      debug_mode: True if the web application is running in debug mode
    """
    traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
    logging.exception(traceback_info)
    email_admins(traceback_info, defer_now=True)

    self.response.clear()
    self.response.set_status(500)
    self.response.out.write(RENDERED_500_PAGE)

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
import sys
from time import sleep
import traceback

# Third-party libraries
from apiclient.discovery import build_from_document
from apiclient.discovery import DISCOVERY_URI
from apiclient.errors import HttpError
import httplib2
from icalendar import Calendar
from oauth2client.appengine import StorageByKeyName
import uritemplate

# App engine specific libraries
from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api import urlfetch_errors
from google.appengine.ext import db
from google.appengine.ext.deferred import defer
from google.appengine.ext.deferred import PermanentTaskFailure
from google.appengine.ext import webapp
from google.appengine import runtime
from webapp2_extras import jinja2

# App specific libraries
from admins import ADMINS_TO
from models import Credentials
from models import Event
from models import TimeKeyword
import secret_key
import time_utils


CALENDAR_ID = 'vhoam1gb7uqqoqevu91liidi80@group.calendar.google.com'
CREDENTIALS_KEYNAME = 'calendar.dat'
RESPONSES = {1: ['once a week', 'week'],
             4: ['every two days', 'two-day'],
             7: ['once a day', 'day'],
             14: ['twice a day', 'half-day'],
             28: ['every six hours', 'six-hrs'],
             56: ['every three hours', 'three-hrs']}
# Without using the kwarg 'app' in get_jinja2, webapp2.get_app() is
# used, which returns the active app instance.
# [Reference: http://webapp-improved.appspot.com/api/webapp2.html]
JINJA2_RENDERER = jinja2.get_jinja2()
RENDERED_500_PAGE = JINJA2_RENDERER.render_template('500.html')
DISCOVERY_DOC_FILENAME = 'calendar_discovery.json'
DISCOVERY_DOC_PARAMS = {'api': 'calendar', 'apiVersion': 'v3'}
FUTURE_LOCATION = ('http://code.google.com/p/google-api-python-client/source/'
                   'browse/apiclient/contrib/calendar/future.json')


class Error(Exception):
  """Base error class for library functions."""


class BadInterval(Error):
  """Error corresponding to an unanticipated number of update intervals."""


class MissingUID(Error):
  """Error corresponding to missing UID in an event."""


class UnexpectedDescription(Error):
  """Error corresponding to an unexpected event description."""


class CredentialsLoadError(Error):
  """Error when credentials are not loaded correctly from a specified file."""


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


def InitCredentials(keyname=CREDENTIALS_KEYNAME):
  """Initializes an OAuth2Credentials object from a file.

  Args:
    keyname: The key name of the credentials object in the data store.

  Returns:
    An OAuth2Credentials object.
  """
  storage = StorageByKeyName(Credentials, keyname, 'credentials')
  credentials = storage.get()

  if credentials is None or credentials.invalid == True:
    EmailAdmins('Credentials in calendar resource not good.', defer_now=True)
    raise CredentialsLoadError('No credentials retrieved.')

  return credentials


def InitService(credentials=None):
  """Initializes a service object to make calendar requests.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials from
        CREDENTIALS_KEYNAME.

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

  with open(DISCOVERY_DOC_FILENAME, 'rU') as fh:
    cached_discovery_doc = fh.read()

  return build_from_document(cached_discovery_doc,
                             DISCOVERY_URI,
                             http=http,
                             developerKey=secret_key.DEVELOPER_KEY)


def AttemptAPIAction(http_verb, num_attempts=3, log_msg=None,
                     credentials=None, **kwargs):
  """Attempt an API action a predetermined number of times before failing.

  Args:
    http_verb: The HTTP verb of the intended request. Examle: get, update.
    num_attempts: The number of attempts to make before failing the request.
        Defaults to 3.
    log_msg: The log message to report upon success. Defaults to None.
    credentials: An OAuth2Credentials object used to build a service object.
    kwargs: The keyword arguments to be passed to the API request.

  Returns:
    The result of the API request
  """
  service = InitService(credentials=credentials)

  # pylint:disable-msg=E1101
  api_action = getattr(service.events(), http_verb, None)
  if api_action is None:
    return None

  attempts = int(num_attempts) if num_attempts > 0 else 0
  while attempts:
    try:
      result = api_action(**kwargs).execute()

      if log_msg is None:
        log_msg = '{id_} changed via {verb}'.format(id_=result['id'],
                                                    verb=http_verb)
      logging.info(log_msg)

      return result
    except (httplib2.HttpLib2Error, HttpError) as exc:
      logging.info(exc)
      attempts -= 1
      sleep(3)

  return None


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
  # If WhiteList is updated, ParseEvent must be as well
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
  uid = event.get('uid', None)
  if uid is None:
    raise MissingUID(event)

  # convert from type icalendar.prop.vText to unicode
  uid = unicode(uid)
  description = unicode(event.get('description', ''))
  location = unicode(event.get('location', ''))

  # The phrase 'No destination specified' does not match its
  # counterpart in the description, so we transform {location}.
  if location == 'No destination specified':
    location = 'an unspecified location'

  # Check description is formed as we expect
  if not uid.startswith('item-'):
    target = ' is in {} '.format(location)
    if description.count(target) != 1:
      raise UnexpectedDescription(description)

    # remove name from the description
    description = 'In {location} {description}'.format(
        location=location, description=description.split(target)[1])

  start_string = time_utils.FormatTime(event.get('dtstart').dt)
  start_keyword = 'dateTime' if start_string.endswith('Z') else 'date'
  start = {start_keyword: start_string}

  end_string = time_utils.FormatTime(event.get('dtend').dt)
  end_keyword = 'dateTime' if end_string.endswith('Z') else 'date'
  end = {end_keyword: end_string}

  summary = unicode(event.get('summary'))
  if not summary:
    summary = 'None'

  sequence = event.get('sequence', None)

  event_data = {'start': start,
                'end': end,
                'summary': summary,
                'location': location,
                'description': description,
                'sequence': sequence}
  return uid, event_data


def RetrieveCalendarDiscoveryDoc(credentials=None):
  """Retrieves the discovery doc for the calendar API service.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials from
        CREDENTIALS_KEYNAME.

  Returns:
    A tuple (success, content) where success is a boolean describing if the doc
        was retrieved successfully and content (if success) contains the JSON
        string contents of the discovery doc
  """
  if credentials is None:
    credentials = InitCredentials()

  http = httplib2.Http()
  http = credentials.authorize(http)

  requested_url = uritemplate.expand(DISCOVERY_URI, DISCOVERY_DOC_PARAMS)
  resp, content = http.request(requested_url)

  success = False
  if resp.status < 400:
    try:
      json.loads(content)
      success = True
    except ValueError:
      pass

  return success, content


def CheckCalendarDiscoveryDoc(credentials=None):
  """Checks a cached discovery doc against the current doc for calendar service.

  If the discovery can't be retrieved or the cached copy disagrees with the
  current version, an email is sent to the administrators.

  Args:
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is None, attempt to get credentials from
        CREDENTIALS_KEYNAME.
  """
  success, current_discovery_doc = RetrieveCalendarDiscoveryDoc(
      credentials=credentials)

  if not success:
    EmailAdmins('Couldn\'t retrieve discovery doc.', defer_now=True)
    return

  with open(DISCOVERY_DOC_FILENAME, 'rU') as fh:
    cached_discovery_doc = fh.read()

  if cached_discovery_doc != current_discovery_doc:
    EmailAdmins('Current discovery doc disagrees with cached version.',
                defer_now=True)


def CheckFutureFeaturesDoc(future_location=FUTURE_LOCATION):
  """Checks if a future features doc for the calendar service exists.

  If a future features doc is detected, an email is sent to the administrators.

  Args:
    future_location: A string URL where the future features doc would reside if
        it existed. This defaults to the constant FUTURE_LOCATION.
  """
  http = httplib2.Http()
  resp, _ = http.request(future_location)

  if resp.status != 404:
    EmailAdmins('Future features JSON responded with {}.'.format(resp.status),
                defer_now=True)


def DeferFunctionDecorator(method):
  """Decorator that allows a function to accept a defer_now argument.

  Args:
    method: a callable object

  Returns:
    A new function which will do the same work as method, will also
        accept a defer_now keyword argument, and will log the arguments
        passed in. In the case that defer_now=True, the new function
        will spawn a task in the deferred queue at /workers.
  """

  def DeferrableMethod(*args, **kwargs):
    """Returned function that uses method from outside scope

    Adds behavior for logging and deferred queue.
    """
    logging.info('{method.func_name} called with: {locals!r}'.format(
        method=method, locals=locals()))

    defer_now = kwargs.pop('defer_now', False)
    if defer_now:
      kwargs['defer_now'] = False
      kwargs['_url'] = '/workers'

      defer(DeferrableMethod, *args, **kwargs)
    else:
      return method(*args, **kwargs)

  return DeferrableMethod


def MonthlyCleanup(relative_date, defer_now=False):
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
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('MonthlyCleanup called with: {!r}'.format(locals()))

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
    msg = ('MonthlyCleanup called with bad date {relative_date} '
           'on {today}.'.format(relative_date=relative_date, today=today))
    logging.info(msg)
    EmailAdmins(msg, defer_now=True)
    return

  prior_date_as_str = time_utils.FormatTime(prior_date)
  old_events = Event.gql('WHERE end_date <= :date', date=prior_date_as_str)
  for event in old_events:
    logging.info('{event} removed from datastore. {event.gcal_edit} '
                 'remains in calendar.'.format(event=event))
    event.delete()


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
        methods will attempt to get credentials from CREDENTIALS_KEYNAME.
  """
  logging.info('UpdateUpcoming called with: {!r}'.format(locals()))

  upcoming.sort()
  if user_cal.upcoming != upcoming:
    now = datetime.datetime.utcnow()
    for uid in user_cal.upcoming:
      if uid not in upcoming:
        event = Event.get_by_key_name(uid)

        # pylint:disable-msg=E1103
        end_date = time_utils.TimeToDTStamp(event.end.value)
        if end_date > now:
          # If federated identity not set, User.__cmp__ only uses email
          event.attendees.remove(user_cal.owner)
          if not event.attendees:
            # pylint:disable-msg=E1101
            log_msg = '{} deleted'.format(event.gcal_edit)
            # pylint:disable-msg=E1101
            AttemptAPIAction('delete', log_msg=log_msg, credentials=credentials,
                             calendarId=CALENDAR_ID, eventId=event.gcal_edit)

            event.delete()  # pylint:disable-msg=E1103
          else:
            # pylint:disable-msg=E1101
            updated_event = AttemptAPIAction('update', credentials=credentials,
                                             calendarId=CALENDAR_ID,
                                             eventId=event.gcal_edit,
                                             body=event.as_dict())
            sequence = updated_event.get('sequence', event.sequence)
            event.sequence = sequence
            event.put()

    user_cal.upcoming = upcoming
    user_cal.put()


# pylint:disable-msg=R0913
def UpdateUserSubscriptions(user_cal, credentials=None, links=None,
                            link_index=0, upcoming=None,
                            last_used_uid=None, defer_now=False):
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
        methods will attempt to get credentials from CREDENTIALS_KEYNAME.
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
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  logging.info('UpdateUserSubscriptions called with: {!r}'.format(locals()))

  if defer_now:
    defer(UpdateUserSubscriptions, user_cal, credentials=credentials,
          links=links, link_index=link_index, upcoming=upcoming,
          last_used_uid=last_used_uid, defer_now=False, _url='/workers')
    return

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
          EmailAdmins(msg, defer_now=True)
  except (runtime.DeadlineExceededError, urlfetch_errors.DeadlineExceededError):
    # NOTE: upcoming has possibly been updated inside the try statement
    defer(UpdateUserSubscriptions, user_cal, credentials=credentials,
          links=links, link_index=index, upcoming=upcoming, last_used_uid=uid,
          defer_now=False, _url='/workers')
    return

  # If the loop completes without timing out
  defer(UpdateUpcoming, user_cal, upcoming,
        credentials=credentials, _url='/workers')


def UpdateSubscription(link, current_user, credentials=None, start_uid=None):
  """Updates the GCal instance with the events in link for the current_user.

  Args:
    link: Link to calendar feed being subscribed to
    current_user: a User instance corresponding to the user that is updating
    credentials: An OAuth2Credentials object used to build a service object.
        In the case the credentials is the default value of None, future
        methods will attempt to get credentials from CREDENTIALS_KEYNAME.
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
        EmailAdmins(msg, defer_now=True)
    else:
      uid, event_data = ParseEvent(component)
      event = Event.get_by_key_name(uid)
      if event is None:
        event_data['attendees'] = [{'email': current_user.email()}]
        cal_event = AttemptAPIAction('insert', credentials=credentials,
                                     calendarId=CALENDAR_ID, body=event_data)

        if cal_event is None:
          yield (uid, False, True)
          continue

        gcal_edit = cal_event['id']
        sequence = cal_event.get('sequence', 0)
        event = Event(key_name=uid,
                      description=db.Text(event_data['description']),
                      start=TimeKeyword.from_dict(event_data['start']),
                      end=TimeKeyword.from_dict(event_data['end']),
                      location=event_data['location'],
                      summary=event_data['summary'],
                      attendees=[current_user],
                      gcal_edit=gcal_edit,
                      sequence=sequence)
        event.put()

        # execution has successfully completed
        yield (uid,
               time_utils.RemoveTimezone(component.get('dtend').dt) > now,
               False)
      else:
        # Spoof existing datapoints from the Event object
        event_data['id'] = event.gcal_edit
        event_data['attendees'] = event.attendee_emails()
        if event_data['sequence'] is None:
          event_data['sequence'] = event.sequence

        # We need to make changes for new event data or a new owner
        if (current_user not in event.attendees or
            event_data != event.as_dict()):
          # Update attendees
          if current_user not in event.attendees:  # pylint:disable-msg=E1103
            event.attendees.append(current_user)  # pylint:disable-msg=E1103
          # pylint:disable-msg=E1103
          event_data['attendees'] = event.attendee_emails()

          # Push all updates to calendar event
          # pylint:disable-msg=E1103
          log_msg = '{} updated'.format(event.gcal_edit)
          updated_event = AttemptAPIAction('update', log_msg=log_msg,
                                           credentials=credentials,
                                           calendarId=CALENDAR_ID,
                                           eventId=event.gcal_edit,
                                           body=event_data)

          # If updated_event is None, we have failed and
          # don't want to add the uid to results
          if updated_event is None:
            yield (uid, False, True)
            continue
          else:
            sequence = updated_event.get('sequence', event_data['sequence'])
            event.sequence = sequence
            event.put()  # pylint:disable-msg=E1103

        # execution has successfully completed
        yield (uid,
               time_utils.RemoveTimezone(component.get('dtend').dt) > now,
               False)

################################################
############# Handler class helper #############
################################################

def EmailAdmins(error_msg, defer_now=False):
  """Sends email to admins with the preferred message, with option to defer.

  Uses the template error_notify.templ to generate an email with the {error_msg}
  sent to the list of admins in admins.ADMINS_TO.

  Args:
    error_msg: A string containing an error to be sent to admins by email
    defer_now: Boolean to determine whether or not a task should be spawned, by
        default this is False.
  """
  if defer_now:
    defer(EmailAdmins, error_msg, defer_now=False, _url='/workers')
    return

  sender = 'Persistent Cal Errors <errors@persistent-cal.appspotmail.com>'
  subject = 'Persistent Cal Error: Admin Notify'
  body = JINJA2_RENDERER.render_template('error_notify.templ', error=error_msg)
  mail.send_mail(sender=sender, to=ADMINS_TO,
                 subject=subject, body=body)


def DeadlineDecorator(method):
  """Decorator for HTTP verbs to handle GAE timeout.

  Args:
    method: a callable object, expected to be a method of an object from
        a class that inherits from webapp.RequestHandler

  Returns:
    A new function which calls {method}, catches certain errors
        and responds to them gracefully
  """

  def WrappedMethod(self, *args, **kwargs):  # pylint:disable-msg=W0142
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
      EmailAdmins(msg, defer_now=True)
    except (runtime.DeadlineExceededError,
            urlfetch_errors.DeadlineExceededError):
      # pylint:disable-msg=W0142
      traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
      logging.exception(traceback_info)
      EmailAdmins(traceback_info, defer_now=True)  # pylint:disable-msg=E1123

      self.response.clear()
      self.response.set_status(500)
      self.response.out.write(RENDERED_500_PAGE)

  return WrappedMethod


class ExtendedHandler(webapp.RequestHandler):
  """A custom version of GAE webapp.RequestHandler.

  This subclass of webapp.RequestHandler defines a handle_exception
  function that will email administrators when an exception
  occurs. In addition, the __new__ method is overridden
  to allow custom wrappers to be placed around the HTTP verbs
  before an instance is created.
  """

  def __new__(cls, *args, **kwargs):  # pylint:disable-msg=W0142
    """Constructs the object.

    This is explicitly intended for Google App Engine's webapp.RequestHandler.
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
        setattr(cls, verb, DeadlineDecorator(method))

    return super(ExtendedHandler, cls).__new__(cls, *args, **kwargs)

  @webapp.cached_property
  def Jinja2(self):
    """Cached property holding a Jinja2 instance."""
    return jinja2.get_jinja2(app=self.app)

  def RenderResponse(self, template, **context):  # pylint:disable-msg=W0142
    """Use Jinja2 instance to render template and write to output.

    Args:
      template: filename (relative to ~/templates) that we are rendering
      context: keyword arguments corresponding to variables in template
    """
    rendered_value = self.Jinja2.render_template(template, **context)
    self.response.write(rendered_value)

  # pylint:disable-msg=C0103,W0613
  def handle_exception(self, exception, debug_mode):
    """Custom handler for all GAE errors that inherit from Exception.

    Args:
      exception: the exception that was thrown
      debug_mode: True if the web application is running in debug mode
    """
    traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
    logging.exception(traceback_info)
    EmailAdmins(traceback_info, defer_now=True)

    self.response.clear()
    self.response.set_status(500)
    self.response.out.write(RENDERED_500_PAGE)

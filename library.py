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
from types import FunctionType as function
from urllib2 import urlopen

# Third-party libraries
import atom
import gdata.calendar.client
import gdata.calendar.data
from gdata.client import RedirectError
import gdata.gauth
from icalendar import Calendar

# App engine specific libraries
from google.appengine.api import mail
from google.appengine.ext import db
from google.appengine.ext.deferred import defer
from google.appengine.ext.deferred import PermanentTaskFailure
from google.appengine.ext.deferred import run
from google.appengine.ext.webapp import RequestHandler
from google.appengine.ext.webapp import template
from google.appengine.runtime import DeadlineExceededError

# App specific libraries
from admins import ADMINS_TO
from models import Event
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET
from secret_key import TOKEN
from secret_key import TOKEN_SECRET


URI = ('https://www.google.com/calendar/feeds/'
       'vhoam1gb7uqqoqevu91liidi80%40group.calendar.google.com/private/full')
RESPONSES = {1: ['once a week', 'week'],
             4: ['every two days', 'two-day'],
             7: ['once a day', 'day'],
             14: ['twice a day', 'half-day'],
             28: ['every six hours', 'six-hrs'],
             56: ['every three hours', 'three-hrs']}
PATH_TO_500_TEMPLATE = os.path.join(os.path.dirname(__file__),
                                    'templates', '500.html')
RENDERED_500_PAGE = template.render(PATH_TO_500_TEMPLATE, {})


def JsonAscii(obj):
  """Returns an object in JSON with ensure_ascii explicitly set True."""
  return simplejson.dumps(obj, ensure_ascii=True)


def UpdateString(update_intervals):
  """Returns a JSON object to represent the frequency of updates."""
  length = len(update_intervals)
  if length not in RESPONSES:
    raise Exception('Bad interval length')
  else:
    return simplejson.dumps(RESPONSES[length])


def InitGCAL():
  """Initializes a calendar client based on a stored auth token."""
  gcal = gdata.calendar.client.CalendarClient(source='persistent-cal')

  auth_token = gdata.gauth.OAuthHmacToken(consumer_key=CONSUMER_KEY,
                                          consumer_secret=CONSUMER_SECRET,
                                          token=TOKEN,
                                          token_secret=TOKEN_SECRET,
                                          auth_state=3)

  gcal.auth_token = auth_token
  return gcal


def ConvertToInterval(timestamp):
  """Converts a datetime timestamp to a time interval for a cron job."""
  # Monday 0, sunday 6
  # 8 intervals in a day, round up hours
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
  """Takes a datetime object and returns a formatted time stamp."""
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
  """Takes time as string and returns a datetime object."""
  # strftime('%Y-%m-%dT%H:%M:%S.000Z') for datetime
  # strftime('%Y-%m-%d') for date

  # Default TZ is UTC/GMT
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
  """Takes time as string (date or datetime) and returns date as string."""
  time_parse = '%Y-%m-%d'
  try:
    converted_val = datetime.datetime.strptime(time_as_str, time_parse)
    return time_as_str
  except ValueError:
    pass

  time_parse += 'T%H:%M:%S.000Z'
  try:
    converted_val = datetime.datetime.strptime(time_as_str, time_parse)
    converted_val = converted_val.date()
    return converted_val.strftime('%Y-%m-%d')
  except ValueError:
    pass


def RemoveTimezone(time_value):
  """Takes a datetime object and removes the timezone."""
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
  """Determines if a link is on the whitelist and transforms it if needed."""
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


def AddOrUpdateEvent(event_data, gcal, email=None,
                     event=None, push_update=True):
  """Create event in main application calendar and add user as attendee."""
  update = (event is not None)
  if not update:
    event = gdata.calendar.data.CalendarEventEntry()

  event.title = atom.data.Title(text=event_data['summary'])
  event.content = atom.data.Content(text=event_data['description'])

  # Where
  event.where.append(gdata.calendar.data.CalendarWhere(
      value=event_data['location']))

  # When
  start_time = event_data['when:from']
  end_time = event_data['when:to']
  event.when.append(gdata.calendar.data.When(start=start_time, end=end_time))

  if update:
    attempts = 3
    if push_update:
      while attempts:
        try:
          gcal.Update(event)
          logging.info('%s updated', event.get_edit_link().href)
          break
        except RedirectError:
          attempts -= 1
          sleep(3)

    # Returns none if event did not get updated (if it needed to)
    return event if attempts else None
  else:
    # Who
    who_add = gdata.calendar.data.EventWho(email=email)
    event.who.append(who_add)

    attempts = 3
    new_event = None
    while attempts:
      try:
        new_event = gcal.InsertEvent(event, insert_uri=URI)
        logging.info('%s was inserted', new_event.get_edit_link().href)
        break
      except RedirectError:
        attempts -= 1
        sleep(3)

    return new_event


def ParseEvent(event):
  """Parses an iCalendar.cal.Event instance to a predefined format."""
  # Assumes event is type icalendar.cal.Event

  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  description = unicode(event.get('description'))
  location = unicode(event.get('location'))
  # No destination specified does not match up
  if location == 'No destination specified':
    location = 'an unspecified location'

  if not uid.startswith('item-'):
    target = ' is in %s ' % location
    if description.count(target) != 1:
      # Since whitelisted, we expect the same format
      raise Exception('Unrecognized event format')

    description = 'In %s %s' % (location, description.split(target)[1])

  event_data = {'when:from': FormatTime(event.get('dtstart').dt),
                'when:to': FormatTime(event.get('dtend').dt),
                'summary': unicode(event.get('summary')),
                'location': location,
                'description': description}
  return uid, event_data


def MonthlyCleanup(relative_date, defer_now=False):
  """Deletes events older than three months.

  Will delete events from the datastore that are older than three months. First
  checks that the date provided is at most two days prior to the current one.

  Note: This would seem to argue that relative_date should not be provided, but
  we want to use the relative_date from the server that is executing the cron
  job, not the one executing the cleanup (as there may be some small
  differences). In the that relative_date does not pass this check, we log and
  send and email to the admins, but do not raise an error. This is done so
  this can be removed from the task queue in the case of the invalid input.

  Args:
    relative_date: date provided by calling script. Expected to be current date
    defer_now: flag to determine whether or not a task should be spawned
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
    # TODO(dhermes) Consider also deleting from main calendar
    # gcal.delete(event.gcal_edit, force=True)
    logging.info('%s removed from datastore. %s remains in calendar.',
                 event, event.gcal_edit)
    event.delete()


def UpdateUpcoming(user_cal, upcoming, gcal):
  """Updates the GCal inst. by deleting events removed from extern. calendar.

  If the new upcoming events list is different from that on the user_cal, it
  will iterate through the difference and delete those events that have not yet
  passed which are still on the calendar.
  Args:
    user_cal:
    upcoming:
    gcal:
  """
  logging.info('%s called with: %s', 'UpdateUpcoming', locals())

  if set(user_cal.upcoming) != set(upcoming):
    now = datetime.datetime.utcnow()
    for uid in set(user_cal.upcoming).difference(upcoming):
      event = Event.get_by_key_name(uid)
      event_data = simplejson.loads(event.event_data)
      if TimeToDTStamp(event_data['when:to']) > now:
        event.who.remove(user_cal.owner.user_id())
        if not event.who:
          gcal.delete(event.gcal_edit, force=True)
          logging.info('%s deleted', event.gcal_edit)
          event.delete()
        else:
          # TODO(dhermes) To avoid two trips to the server, reconstruct
          #               the CalendarEventEntry from the data in event
          #               rather than using GET
          cal_event = gcal.GetEventEntry(uri=event.gcal_edit)
          # Filter out this user
          cal_event.who = [who_entry for who_entry in cal_event.who
                           if who_entry.email != user_cal.owner.email()]
          gcal.Update(cal_event)
          event.put()
    user_cal.upcoming = list(set(upcoming))
    user_cal.put()


def UpdateUserSubscriptions(links, user_cal, gcal, upcoming=None,
                            defer_now=False, start=None):
  """Updates a list of calendars for a user, with a call to self on timeout."""
  logging.info('%s called with: %s', 'UpdateUserSubscriptions', locals())
  upcoming = [] if upcoming is None else upcoming
  start = {} if start is None else start

  if defer_now:
    defer(UpdateUserSubscriptions, links, user_cal, gcal,
          upcoming=upcoming, defer_now=False, start=start, _url='/workers')
    return

  # Set variables to pick up where the loop left off in case of DLExcError
  index = 0
  uid = None

  try:
    for index, link in enumerate(links):
      # In the case a uid is not None, we are picking up in the middle
      # if the feed for the first link
      if index == 0 and link == start.get('link', '') and 'uid' in start:
        uid_generator = UpdateSubscription(link, user_cal.owner,
                                           gcal, start_uid=start['uid'])
      else:
        uid_generator = UpdateSubscription(link, user_cal.owner, gcal)

      for uid, is_upcoming, failed in uid_generator:
        if is_upcoming:
          upcoming.append(uid)
        elif failed:
          logging.info('silently failed operation on %s from %s', uid, link)
          email_admins('silently failed operation on %s from %s' % (uid, link),
                       defer_now=True)
  except DeadlineExceededError:
    # update links to account for progress
    # upcoming is also updated along the way
    links = links[index:]
    start = {'uid': uid, 'link': links[0]}
    defer(UpdateUserSubscriptions, links, user_cal, gcal,
          upcoming=upcoming, defer_now=defer_now, start=start, _url='/workers')
    return

  # If the loop completes without timing out
  defer(UpdateUpcoming, user_cal, upcoming, gcal, _url='/workers')
  return


def UpdateSubscription(link, current_user, gcal, start_uid=None):
  """Updates the GCal instance with the events in link for the current_user.

  Returns a generator instance which yields (uid, bool) tuples where bool
  is true if the event at uid is upcoming
  Args:
    link:
    current_user:
    gcal:
    start_uid:
  """
  logging.info('%s called with: %s', 'UpdateSubscription', locals())

  current_user_id = current_user.user_id()

  valid, link = WhiteList(link)
  if not valid:
    # Do nothing if not on the whitelist
    # http://www.python.org/dev/peps/pep-0255/ (Specification: Return)
    return

  import_feed = urlopen(link)
  ical = Calendar.from_string(import_feed.read())
  import_feed.close()

  now = datetime.datetime.utcnow()

  start_index = 0
  if start_uid is not None:
    uid_list = [component.get('uid', '') for component in ical.walk()]
    if uid_list.count(start_uid) > 0:
      start_index = uid_list.index(start_uid)

  for component in ical.walk()[start_index:]:
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
        cal_event = AddOrUpdateEvent(event_data, gcal,
                                     email=current_user.email())
        # TODO(dhermes) add to failed queue to be updated by a cron
        if cal_event is None:
          yield (uid, False, True)
          continue

        gcal_edit = cal_event.get_edit_link().href
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
              cal_event = gcal.GetEventEntry(uri=event.gcal_edit)
              logging.info('GET sent to %s', event.gcal_edit)
              break
            except RedirectError:
              attempts -= 1
              sleep(3)

          # TODO(dhermes) add to failed queue to be updated by a cron
          if cal_event is None:
            yield (uid, False, True)
            continue

          # Update who
          if current_user_id not in event.who:
            event.who.append(current_user_id)  # id is string

            # add existing event to current_user's calendar
            who_add = gdata.calendar.data.EventWho(email=current_user.email())
            cal_event.who.append(who_add)

          # Update existing event
          if db.Text(JsonAscii(event_data)) != event.event_data:
            event.event_data = db.Text(JsonAscii(event_data))

            # Don't push update to avoid pushing twice (if both changed)
            AddOrUpdateEvent(event_data,
                             gcal,
                             event=cal_event,
                             push_update=False)
            # push_update=False, impossible to have RedirectError

          # Push all updates to calendar event
          attempts = 3
          while attempts:
            try:
              gcal.Update(cal_event)
              logging.info('%s updated', cal_event.get_edit_link().href)

              # After all possible changes to the Event instance have occurred
              event.put()
              break
            except RedirectError:
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

def email_admins(traceback_info, defer_now=False):
  """Sends email to admins with the preferred message, with option to defer."""
  if defer_now:
    defer(email_admins, traceback_info, defer_now=False, _url='/workers')
    return

  sender = 'Persistent Cal Errors <errors@persistent-cal.appspotmail.com>'
  subject = 'Persistent Cal Error: Admin Notify'
  email_path = os.path.join(os.path.dirname(__file__),
                            'templates', 'error_notify.templ')
  body = template.render(email_path, {'error': traceback_info})
  mail.send_mail(sender=sender, to=ADMINS_TO,
                 subject=subject, body=body)


def deadline_decorator(method):
  """Decorator for HTTP verbs to handle GAE timeout."""

  def wrapped_method(self, *args, **kwargs):
    try:
      method(self, *args, **kwargs)
    except PermanentTaskFailure:
      # In this case, the function can't be run, so we alert but do not
      # raise the error, returning a 200 status code, hence killing the task.
      msg = 'Permanent failure attempting to execute task'
      logging.exception(msg)
      email_admins(msg, defer_now=True)
    except DeadlineExceededError:
      traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
      logging.exception(traceback_info)
      email_admins(traceback_info, defer_now=True)

      self.response.clear()
      self.response.set_status(500)
      self.response.out.write(RENDERED_500_PAGE)

  return wrapped_method


class DecorateHttpVerbsMetaclass(type):
  """Metaclass to decorate all HTTP verbs with a special method."""

  def __new__(cls, name, parents, cls_attr):
    """Constructs the object.

    This is explicitly intended for Google App Engine's RequestHandler.
    Requests only suport 7 of the 9 HTTP verbs, 4 of which we will
    decorate: get, post, put and delete. The other three supported
    (head, options, trace) may be added at a later time.
    Args:
      name:
      parents:
      cls_attr:

    Reference: ('http://code.google.com/appengine/docs/python/tools/'
                'webapp/requesthandlerclass.html')
    """
    verbs = ['get', 'post', 'put', 'delete']
    for verb in verbs:
      if verb in cls_attr and isinstance(cls_attr[verb], function):
        cls_attr[verb] = deadline_decorator(cls_attr[verb])

    return super(DecorateHttpVerbsMetaclass, cls).__new__(cls, name,
                                                          parents, cls_attr)


class ExtendedHandler(RequestHandler):
  __metaclass__ = DecorateHttpVerbsMetaclass

  def handle_exception(self, exception, debug_mode):
    traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
    logging.exception(traceback_info)
    email_admins(traceback_info, defer_now=True)

    self.response.clear()
    self.response.set_status(500)
    self.response.out.write(RENDERED_500_PAGE)


# TODO(dhermes) make proposed change to AppEngine by calling super().post
class TaskHandler(RequestHandler):
  """A {borrowed} webapp handler class that processes deferred invocations."""

  def post(self):
    """Handles task queue POST requests."""
    if 'X-AppEngine-TaskName' not in self.request.headers:
      logging.critical('Detected an attempted XSRF attack. The header '
                       '"X-AppEngine-Taskname" was not set.')
      self.response.set_status(403)
      return

    in_prod = (
        not self.request.environ.get('SERVER_SOFTWARE').startswith('Devel'))
    if in_prod and self.request.environ.get('REMOTE_ADDR') != '0.1.0.2':
      logging.critical('Detected an attempted XSRF attack. This request did '
                       'not originate from Task Queue.')
      self.response.set_status(403)
      return

    headers = ['%s:%s' % (k, v) for k, v in self.request.headers.items()
               if k.lower().startswith('x-appengine-')]
    logging.info(', '.join(headers))

    run(self.request.body)

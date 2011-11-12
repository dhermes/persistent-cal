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


"""Extended function library for request handlers for persistent-cal"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import datetime
import logging
import re
import simplejson
from time import sleep
from urllib2 import urlopen

# Third-party libraries
import atom
import gdata.gauth
import gdata.calendar.client
import gdata.calendar.data
from gdata.client import RedirectError
from icalendar import Calendar

# App engine specific libraries
from google.appengine.ext import db

# App specific libraries
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


def JsonAscii(obj):
  """Returns an object in JSON with ensure_ascii explicitly set True"""
  return simplejson.dumps(obj, ensure_ascii=True)

def UpdateString(update_intervals):
  """Returns a JSON object to represent the frequency of updates"""
  length = len(update_intervals)
  if length not in RESPONSES:
    raise Exception('Bad interval length')
  else:
    return simplejson.dumps(RESPONSES[length])


def InitGCAL():
  """Initializes a calendar client based on a stored auth token"""
  gcal = gdata.calendar.client.CalendarClient(source='persistent-cal')

  auth_token = gdata.gauth.OAuthHmacToken(consumer_key=CONSUMER_KEY,
                                          consumer_secret=CONSUMER_SECRET,
                                          token=TOKEN,
                                          token_secret=TOKEN_SECRET,
                                          auth_state=3)

  gcal.auth_token = auth_token
  return gcal


def ConvertToInterval(timestamp):
  """Converts a datetime timestamp to a time interval for a cron job"""
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
  """Takes a datetime object and returns a formatted time stamp"""
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
  """Takes time as string and returns a datetime object"""
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


def RemoveTimezone(time_value):
  """Takes a datetime object and removes the timezone"""
  if isinstance(time_value, datetime.datetime):
    if time_value.tzinfo is not None:
      time_parse = '%Y-%m-%dT%H:%M:%S.%fZ'
      time_value = time_value.strftime(time_parse) # TZ is lost
      time_value = datetime.datetime.strptime(time_value, time_parse)
  return time_value


def WhiteList(link):
  """Determines if a link is on the whitelist and transforms it if needed"""
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


def AddOrUpdateEvent(event_data, gcal, event=None, push_update=True):
  """Create event in main application calendar and add user as attendee"""
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
          break
        except RedirectError:
          attempts -= 1
          sleep(3)
          pass

    # Returns none if event did not get updated (if it needed to)
    return event if attempts else None
  else:
    # Who
    who_add = gdata.calendar.data.EventWho(email=event_data['email'])
    event.who.append(who_add)

    attempts = 3
    new_event = None
    while attempts:
      try:
        new_event = gcal.InsertEvent(event, insert_uri=URI)
        break
      except RedirectError:
        attempts -= 1
        sleep(3)
        pass

    return new_event


def ParseEvent(event):
  """Parses an iCalendar.cal.Event instance to a predefined format"""
  # Assumes event is type icalendar.cal.Event

  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  description = unicode(event.get('description'))
  location = unicode(event.get('location'))
  # No destination specified does not match up
  if location == 'No destination specified':
    location = 'an unspecified location'

  # # WITNESS:
  # 4754cd75888cac4a53c7cf003980e195b46dc9fd@tripit.com
  # via 3F43994D-4591D1AA4C63B1472D8D5D0E9568E5A8/tripit.ics
  # description: Daniel Hermes is in San Diego, CA from Sep 1...
  # and via 4A025929-DCB74CB87F330487615696811896215A/tripit.ics
  # description: Sharona Franko is in San Diego, CA from Sep 1...
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


def UpdateSubscription(link, current_user, gcal):
  """
  Updates the GCal instance with the events in link for the current_user

  Returns a list of all uid's for events which have yet to occur (can be used
  to delete removed events)
  """
  result = []
  current_user_id = current_user.user_id()

  valid, link = WhiteList(link)
  if not valid:
    # Do nothing if not on the whitelist
    return result

  import_feed = urlopen(link)
  ical = Calendar.from_string(import_feed.read())
  import_feed.close()

  now = datetime.datetime.utcnow()
  for component in ical.walk():
    if component.name != 'VEVENT':
      logging.info('iCal at % has unexpected event type %s' % (
        link, component.name))
    else:
      uid, event_data = ParseEvent(component)
      event = Event.get_by_key_name(uid)
      if event is None:
        # Create new event
        # (leaving out the event argument creates a new event)
        event_data['email'] = current_user.email()
        cal_event = AddOrUpdateEvent(event_data, gcal)
        # TODO(dhermes) add to failed queue to be updated by a cron
        if cal_event is None:
          continue

        gcal_edit = cal_event.get_edit_link().href
        event = Event(key_name=uid,
                      who=[current_user_id],  # id is string
                      event_data=db.Text(JsonAscii(event_data)),
                      gcal_edit=gcal_edit)
        event.put()

        # execution has successfully completed
        # TODO(dhermes) catch error on get call below
        if RemoveTimezone(component.get('dtend').dt) > now:
          result.append(uid)
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
              break
            except RedirectError:
              attempts -= 1
              sleep(3)
              pass

          # TODO(dhermes) add to failed queue to be updated by a cron
          if cal_event is None:
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
          new_event = None
          while attempts:
            try:
              gcal.Update(cal_event)

              # After all possible changes to the Event instance have occurred
              event.put()
              break
            except RedirectError:
              attempts -= 1
              sleep(3)
              pass

          # If attempts is 0, we have failed and don't want to add the
          # uid to results
          if attempts == 0:
            continue

        # execution has successfully completed
        # TODO(dhermes) catch error on get call below
        if RemoveTimezone(component.get('dtend').dt) > now:
          result.append(uid)

  return result


def UpdateUpcoming(user_cal, upcoming, gcal):
  """
  Updates the GCal instance by deleting pending events removed from ext calendar

  If the new upcoming events list is different from that on the user_cal, it
  will iterate through the difference and delete those events that have not yet
  passed which are still on the calendar.
  """
  if user_cal.upcoming != upcoming:
    now = datetime.datetime.utcnow()
    for uid in set(user_cal.upcoming).difference(upcoming):
      event = Event.get_by_key_name(uid)
      event_data = simplejson.loads(event.event_data)
      if TimeToDTStamp(event_data['when:to']) > now:
        gcal.delete(event.gcal_edit, force=True)
        event.delete()
    user_cal.upcoming = upcoming
    user_cal.put()

import simplejson
with open('db_events.json', 'rb') as fh:
  data = simplejson.load(fh)
for key, value in data.items():
  event_data = simplejson.loads(value['event_data'])
  print event_data['when:to']
  print TimeToDTStamp(event_data['when:to']), '\n'
  print event_data['when:from']
  print TimeToDTStamp(event_data['when:from']), '\n'

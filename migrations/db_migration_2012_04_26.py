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


"""DB migration for Model Update on 2012-04-26.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from db_migration_2012_04_26 import UpdateEvents
s~persistent-cal> UpdateEvents()
"""


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import json

# App specific libraries
from models import Event
from models import TimeKeyword
from models import UserCal


def GetUserDict():
  """Gets a user dictionary based on current state of UserCal DB."""
  user_dict = {}

  user_cals = UserCal.all()
  for user_cal in user_cals:
    user = user_cal.owner

    uid = user.user_id()
    if uid in user_dict:
      raise Exception('Key collision: %s' % uid)

    user_dict[uid] = user

  return user_dict


def TransformEventData(event, user_dict):
  """Takes Event object to new specification."""
  # First make a copy
  new_event = Event(key_name=event.key().name(),
                    who=event.who,
                    event_data=event.event_data,
                    end_date=event.end_date,
                    gcal_edit=event.gcal_edit)


  event_data = json.loads(event.event_data)

  # Add in new (also non-required) attributes
  new_event.description = event_data['description']
  new_event.location = event_data['location']
  new_event.summary = event_data['summary']

  start = event_data['start']
  if not isinstance(start, dict) or len(start) != 1:
    raise Exception('Start not singleton dictionary')
  key = start.keys()[0]
  start_tkw = TimeKeyword(keyword=key, value=start[key])
  new_event.start = start_tkw

  end = event_data['end']
  if not isinstance(end, dict) or len(end) != 1:
    raise Exception('End not singleton dictionary')
  key = end.keys()[0]
  end_tkw = TimeKeyword(keyword=key, value=end[key])
  new_event.end = end_tkw

  new_event.attendees = [user_dict[uid] for uid in event.who]

  return new_event


def UpdateEvents():
  user_dict = GetUserDict()

  events = Event.all()
  for event in events:
    new_event = TransformEventData(event, user_dict)
    new_event.put()

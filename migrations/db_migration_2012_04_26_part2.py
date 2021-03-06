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
s~persistent-cal> from db_migration_2012_04_26_part2 import UpdateEvents
s~persistent-cal> UpdateEvents()
"""


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import json

# App specific libraries
from models import Event


def UpdateEvents():
  events = Event.all()
  for event in events:
    new_event = Event(key_name=event.key().name(),
                      who=event.who,
                      event_data=event.event_data,
                      description=event.description,
                      start=event.start,
                      end=event.end,
                      location=event.location,
                      summary=event.summary,
                      attendees=event.attendees,
                      gcal_edit=event.gcal_edit)
    new_event.put()

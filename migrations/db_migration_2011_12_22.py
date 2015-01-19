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


"""DB migration for Model Update on 2011-12-22.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from db_migration_2011_12_22 import UpdateEvents
s~persistent-cal> UpdateEvents()

Note:
  Since pre-migration, each event in the DB will not have an end_date. In
  order to account for this, we temporarily change the model from

    end_date = db.StringProperty(required=True)

  to

    end_date = db.StringProperty(default='01-01-1970', required=True)

  for the purposes of this migration.
"""


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import datetime
import json

# App engine specific libraries
from google.appengine.ext import db

# App specific libraries
from library import JsonAscii
from models import Event


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

  raise Exception('StringToDayString failed with %s' % time_as_str)


def UpdateEvents():
  events = Event.all()
  for event in events:
    event_data = json.loads(event.event_data)

    # removing email, irrelevant
    event_data.pop('email', None)
    event.event_data = db.Text(JsonAscii(event_data))

    # adding new column 'end_date'
    end_date = StringToDayString(event_data['when:to'])
    event.end_date = end_date

    event.put()

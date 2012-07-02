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


"""DB migration for to remove who and event_data from Event.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import os
s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> # or sys.path.append(os.getcwd())
s~persistent-cal> os.environ['HTTP_HOST'] = 'persistent-cal.appspot.com'
s~persistent-cal> from db_migration_2012_07_02 import UpdateEvents
s~persistent-cal> UpdateEvents()
"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import json

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import ndb

# App specific libraries
import models


class TimeKeyword(db.Model):  # pylint:disable-msg=R0904
  """Dummy TimeKeyword model for migration."""
  keyword = db.StringProperty(required=True)
  value = db.StringProperty(required=True)


class TimeKeywordProperty(db.Property):
  """Property for representing Dummy TimeKeyword object."""

  data_type = TimeKeyword

  # pylint:disable-msg=C0103
  def get_value_for_datastore(self, model_instance):
    time_val = super(TimeKeywordProperty, self).get_value_for_datastore(
        model_instance)
    return json.dumps(time_val.as_dict())

  # pylint:disable-msg=C0103
  def make_value_from_datastore(self, value):
    try:
      value_dict = json.loads(value)
      if isinstance(value_dict, dict) and len(value_dict) == 1:
        key = value_dict.keys()[0]
        return TimeKeyword(keyword=key,
                           value=value_dict[key])
    except ValueError:
      pass
    return None

  # pylint:disable-msg=C0103
  def validate(self, value):
    if value is not None and not isinstance(value, TimeKeyword):
      raise db.BadValueError(
          'Property {name} must be convertible to a '
          'TimeKeyword instance ({value}).'.format(name=self.name, value=value))
    return super(TimeKeywordProperty, self).validate(value)

  # pylint:disable-msg=C0103
  def empty(self, value):
    return not value


class Event(db.Model):  # pylint:disable-msg=R0904
  """Dummy Event model for migration."""
  description = db.TextProperty(default='')
  start = TimeKeywordProperty(required=True)
  end = TimeKeywordProperty(required=True)
  location = db.StringProperty(default='')
  summary = db.StringProperty(required=True)
  attendees = db.ListProperty(users.User, required=True)
  gcal_edit = db.StringProperty()
  sequence = db.IntegerProperty(default=0)


def TransformEvent(event):
  """Takes Event object to new specification."""
  uid = event.key().name()
  end = models.TimeKeyword(keyword=event.end.keyword,
                           value=event.end.value)
  start = models.TimeKeyword(keyword=event.start.keyword,
                             value=event.start.value)

  new_event = models.Event(key=ndb.Key(models.Event, uid),
                           description=event.description,
                           start=start,
                           end=end,
                           location=event.location,
                           summary=event.summary,
                           attendees=event.attendees,
                           gcal_edit=event.gcal_edit,
                           sequence=event.sequence)

  return new_event


def UpdateEvents():
  """Updates events."""
  events = Event.all()
  for event in events:
    new_event = TransformEvent(event)
    new_event.put()

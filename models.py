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


"""Model classes for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import datetime
import json

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db

# App specific libraries
import time_utils


class TimeKeyword(db.Model):
  keyword = db.StringProperty(required=True)
  value = db.StringProperty(required=True)

  @classmethod
  def from_dict(cls, time_dict):
    if not isinstance(time_dict, dict) or len(time_dict) != 1:
      raise BadValueError('Requires a dictionary with a single key.')
    key = time_dict.keys()[0]

    return TimeKeyword(keyword=key, value=time_dict[key])

  def _as_dict(self):
    return {self.keyword: self.value}

  def __repr__(self):
    return 'TimeKeyword(%s)' % repr(self._as_dict())


class TimeKeywordProperty(db.Property):

  data_type = TimeKeyword

  def get_value_for_datastore(self, model_instance):
    time_val = super(TimeKeywordProperty, self).get_value_for_datastore(
        model_instance)
    return json.dumps(time_val._as_dict())

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

  def validate(self, value):
    if value is not None and not isinstance(value, TimeKeyword):
      raise BadValueError('Property %s must be convertible '
                          'to a TimeKeyword instance (%s).' %
                          (self.name, value))
    return super(TimeKeywordProperty, self).validate(value)

  def empty(self, value):
    return not value


class Event(db.Model):
  """Holds data for a calendar event (including shared attendees)."""
  # grep -r who .
  # db.to_dict(model_instance, dictionary=None):
  who = db.StringListProperty(required=True)  # hold owner ids as strings
  event_data = db.TextProperty(required=True)  # python dict as json
  description = db.TextProperty(required=True)
  start = TimeKeywordProperty(required=True)
  end = TimeKeywordProperty(required=True)
  location = db.StringProperty(required=True)
  summary = db.StringProperty(required=True)
  attendees = db.ListProperty(users.User, required=True)
  gcal_edit = db.StringProperty(required=True)

  @db.ComputedProperty
  def end_date(self):
    return time_utils.StringToDayString(self.end.value)

  def _as_dict(self):
    attendees = [{'email': attendee.email()} for attendee in self.attendees]
    return {'start': self.start._as_dict(),
            'end': self.end._as_dict(),
            'summary': self.summary,
            'location': self.location,
            'description': self.description,
            'id': self.gcal_edit,
            'attendees': attendees}

  def __repr__(self):
    return 'Event(name=%s)' % self.key().name()

# In a query, comparing a list property to a value performs the test against the
# members of the list: list_property = value tests whether the value appears
# anywhere in the list, list_property < value tests whether any of the list
# members are less than the given value, and so forth.

class UserCal(db.Model):
  """Holds data for a calendar event (including shared owners)."""
  owner = db.UserProperty(required=True)
  # hold calendar feed link as strings
  calendars = db.StringListProperty(required=True)
  # See ('http://code.google.com/appengine/docs/python/datastore/'
  #      'typesandpropertyclasses.html#ListProperty')
  # int defaults to long, so I'll use long
  update_intervals = db.ListProperty(long, required=True)
  upcoming = db.ListProperty(str, required=True)

  def __repr__(self):
    return 'UserCal(owner=%s,name=%s)' % (self.owner.email(), self.key().name())

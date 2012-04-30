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


"""Model classes for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import json

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db

# App specific libraries
import time_utils


class TimeKeyword(db.Model):  # pylint:disable-msg=R0904
  """Model for representing a time with an associated keyword as well.

  This is in place because the API specification calls for times to be
  represented as {'dateTime': '2012-01-01T12:00:00.000Z'} or
  {'date': '2012-01-01'}, so both the string value and the keyword are
  useful to keep around.
  """
  keyword = db.StringProperty(required=True)
  value = db.StringProperty(required=True)

  @classmethod
  def from_dict(cls, time_dict):  # pylint:disable-msg=C0103
    """Class method that returns a new TimeKeyword object given a dictionary.

    It reverses the behavior in TimeKeyword.as_dict and creates a new instance
    using the key of the singleton dictionary as keyword and the value as value.
    """
    if not isinstance(time_dict, dict) or len(time_dict) != 1:
      raise db.BadValueError('Requires a dictionary with a single key.')
    key = time_dict.keys()[0]

    return TimeKeyword(keyword=key, value=time_dict[key])

  def as_dict(self):  # pylint:disable-msg=C0103
    """Returns the TimeKeyword as a dictionary with keyword as key for value."""
    return {self.keyword: self.value}

  def __repr__(self):
    return 'TimeKeyword(%s)' % repr(self.as_dict())


class TimeKeywordProperty(db.Property):
  """Property for representing TimeKeyword objects on a db.Model."""

  data_type = TimeKeyword

  def get_value_for_datastore(self, model_instance):  # pylint:disable-msg=C0103
    time_val = super(TimeKeywordProperty, self).get_value_for_datastore(
        model_instance)
    return json.dumps(time_val.as_dict())

  def make_value_from_datastore(self, value):  # pylint:disable-msg=C0103
    try:
      value_dict = json.loads(value)
      if isinstance(value_dict, dict) and len(value_dict) == 1:
        key = value_dict.keys()[0]
        return TimeKeyword(keyword=key,
                           value=value_dict[key])
    except ValueError:
      pass

    return None

  def validate(self, value):  # pylint:disable-msg=C0103
    if value is not None and not isinstance(value, TimeKeyword):
      raise db.BadValueError('Property %s must be convertible '
                             'to a TimeKeyword instance (%s).' %
                             (self.name, value))
    return super(TimeKeywordProperty, self).validate(value)

  def empty(self, value):  # pylint:disable-msg=C0103
    return not value


class Event(db.Model):  # pylint:disable-msg=R0904
  """Holds data for a calendar event (including shared attendees)."""
  description = db.TextProperty(default='')
  start = TimeKeywordProperty(required=True)
  end = TimeKeywordProperty(required=True)
  location = db.StringProperty(default='')
  summary = db.StringProperty(required=True)
  attendees = db.ListProperty(users.User, required=True)
  gcal_edit = db.StringProperty(required=True)

  @db.ComputedProperty
  def end_date(self):  # pylint:disable-msg=C0103
    """Derived property that turns end into a date string."""
    return time_utils.StringToDayString(self.end.value)

  def attendee_emails(self):  # pylint:disable-msg=C0103
    """Returns a list of dictionaries corresponding to attendee emails."""
    return [{'email': attendee.email()} for attendee in self.attendees]

  def as_dict(self):  # pylint:disable-msg=C0103
    """Returns the Event as a dictionary corresponding to the API spec."""
    return {'start': self.start.as_dict(),
            'end': self.end.as_dict(),
            'summary': self.summary,
            'location': self.location,
            'description': self.description,
            'id': self.gcal_edit,
            'attendees': self.attendee_emails()}

  def __repr__(self):
    return 'Event(name=%s)' % self.key().name()

# In a query, comparing a list property to a value performs the test against the
# members of the list: list_property = value tests whether the value appears
# anywhere in the list, list_property < value tests whether any of the list
# members are less than the given value, and so forth.

class UserCal(db.Model):  # pylint:disable-msg=R0904
  """Holds data for a calendar event (including shared owners)."""
  owner = db.UserProperty(required=True)
  # hold calendar feed link as strings
  calendars = db.StringListProperty(required=True)
  # See ('http://code.google.com/appengine/docs/python/datastore/'
  #      'typesandpropertyclasses.html#ListProperty')
  # int defaults to long, so I'll use long
  update_intervals = db.ListProperty(long, required=True)
  upcoming = db.ListProperty(str, required=True)

  def put(self):  # pylint:disable-msg=C0103
    self.upcoming = sorted(set(self.upcoming))
    super(UserCal, self).put()

  def __repr__(self):
    return 'UserCal(owner=%s,name=%s)' % (self.owner.email(), self.key().name())

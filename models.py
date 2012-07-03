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
import datetime
import logging

# App engine specific libraries
from google.appengine.ext import ndb

# App specific libraries
from custom_exceptions import InappropriateAPIAction
from custom_exceptions import MissingUID
from custom_exceptions import UnexpectedDescription
from google_api_utils import AttemptAPIAction
import time_utils


CALENDAR_ID = 'vhoam1gb7uqqoqevu91liidi80@group.calendar.google.com'


class TimeKeyword(ndb.Model):  # pylint:disable-msg=R0904
  """Model for representing a time with an associated keyword as well.

  This is in place because the API specification calls for times to be
  represented as {'dateTime': '2012-01-01T12:00:00.000Z'} or
  {'date': '2012-01-01'}, so both the string value and the keyword are
  useful to keep around.
  """
  # pylint:disable-msg=E1101
  keyword = ndb.StringProperty(required=True)
  value = ndb.StringProperty(required=True)

  @classmethod
  # pylint:disable-msg=C0103
  def from_ical_event(cls, ical_event, ical_attr):
    """Class method to parse a TimeKeyword from an ical_event and keyword.

    It creates a new instance, parsing the value from the ical_event using the
    ical_attr provided.

    Args:
      ical_event: an icalendar.cal.Event object to be parsed
      ical_attr: The attribute to be parsed from the iCal instance

    Returns:
      An instance of TimeKeyword from the parsing
    """
    value = time_utils.FormatTime(ical_event.get(ical_attr).dt)
    keyword = 'dateTime' if value.endswith('Z') else 'date'
    return cls(keyword=keyword, value=value)

  def as_dict(self):  # pylint:disable-msg=C0103
    """Returns the TimeKeyword as a dictionary with keyword as key for value."""
    return {self.keyword: self.value}

  def to_datetime(self):  # pylint:disable-msg=C0103
    """Returns the TimeKeyword as a datetime.datetime.

    This will likely throw an error if keyword is not one of date or dateTime.

    Returns:
      A datetime.datetime instance parsed from the values
    """
    time_parse = None
    if self.keyword == 'date':
      time_parse = '%Y-%m-%d'
    elif self.keyword == 'dateTime':
      time_parse = '%Y-%m-%dT%H:%M:%S.000Z'

    return datetime.datetime.strptime(self.value, time_parse)

  def __eq__(self, other):
    """Custom equality function using only the attributes.

    Args:
      other: The other value to be compared against
    """
    if not isinstance(other, TimeKeyword):
      return False
    return self.keyword == other.keyword and self.value == other.value

  def __ne__(self, other):
    """Custom negation of equality function using only the attributes.

    Args:
      other: The other value to be compared against
    """
    return not self.__eq__(other)

  def __repr__(self):
    return 'TimeKeyword({!r})'.format(self.as_dict())


def ConvertedDescription(ical_event):
  """Parses and converts a description from an iCal event.

  Args:
    ical_event: an icalendar.cal.Event object to be parsed

  Returns:
    Two strings description and location parsed from {ical_event}
  """
  uid = unicode(ical_event.get('uid', ''))
  description = unicode(ical_event.get('description', ''))
  location = unicode(ical_event.get('location', ''))

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

  return description, location


class Event(ndb.Model):  # pylint:disable-msg=R0904
  """Holds data for a calendar event (including shared attendees)."""
  # pylint:disable-msg=E1101
  description = ndb.TextProperty(default='')
  start = ndb.StructuredProperty(TimeKeyword, required=True)
  end = ndb.StructuredProperty(TimeKeyword, required=True)
  location = ndb.StringProperty(default='')
  summary = ndb.StringProperty(required=True)
  attendees = ndb.UserProperty(repeated=True)
  gcal_edit = ndb.StringProperty()
  sequence = ndb.IntegerProperty(default=0)

  def insert(self, credentials=None):  # pylint:disable-msg=C0103
    """Will insert the event into GCal and then put the values into datastore.

    Args:
      credentials: An OAuth2Credentials object used to build a service object.
          In the case the credentials is the default value of None, future
          methods will attempt to get credentials from the default credentials.

    Returns:
      A boolean value indicating whether the operation was successful.

    Raises:
      InappropriateAPIAction in the case that a corresponding GCal event has
          already been inserted
    """
    if self.gcal_edit is not None:
      raise InappropriateAPIAction('Insert attempted when id already set.')

    event_data = self.as_dict()
    event_data.pop('id')

    inserted_event = AttemptAPIAction('insert', credentials=credentials,
                                      calendarId=CALENDAR_ID, body=event_data)
    if inserted_event is None:
      return False  # failed

    self.gcal_edit = inserted_event['id']
    self.sequence = inserted_event.get('sequence', 0)
    self.put()

    return True

  def update(self, credentials=None):  # pylint:disable-msg=C0103
    """Will update the event in GCal and then put updated values to datastore.

    Args:
      credentials: An OAuth2Credentials object used to build a service object.
          In the case the credentials is the default value of None, future
          methods will attempt to get credentials from the default credentials.

    Returns:
      A boolean value indicating whether the operation was successful.

    Raises:
      InappropriateAPIAction in the case that there is no GCal event to update
    """
    if self.gcal_edit is None:
      raise InappropriateAPIAction('Update attempted when id not set.')

    log_msg = '{} updated'.format(self.gcal_edit)
    updated_event = AttemptAPIAction('update', log_msg=log_msg,
                                     credentials=credentials,
                                     calendarId=CALENDAR_ID,
                                     eventId=self.gcal_edit,
                                     body=self.as_dict())

    if updated_event is None:
      return False  # failed

    sequence = updated_event.get('sequence', None)
    if sequence is not None:
      self.sequence = sequence
    self.put()

    return True

  # pylint:disable-msg=C0103,W0221
  def delete(self, credentials=None):
    """Will delete the event in GCal and then delete from the datastore.

    Args:
      credentials: An OAuth2Credentials object used to build a service object.
          In the case the credentials is the default value of None, future
          methods will attempt to get credentials from the default credentials.

    Raises:
      InappropriateAPIAction in the case that there is no GCal event to delete
    """
    if self.gcal_edit is None:
      raise InappropriateAPIAction('Update attempted when id not set.')

    log_msg = '{} deleted'.format(self.gcal_edit)
    delete_response = AttemptAPIAction('delete', log_msg=log_msg,
                                       credentials=credentials,
                                       calendarId=CALENDAR_ID,
                                       eventId=self.gcal_edit)
    if delete_response is None:
      return

    super(Event, self).delete()

  @classmethod
  # pylint:disable-msg=C0103
  def from_ical_event(cls, ical_event, current_user, credentials=None):
    """Class method to update/add an event from an ical_event.

    It either retrieves an existing instance and updates it, or if no such
    object exists, creates a new one with the attributes from the ical_event.

    Args:
      ical_event: an icalendar.cal.Event object to be parsed
      current_user: a User instance corresponding to the user that is updating
      credentials: An OAuth2Credentials object used to build a service object.
          In the case the credentials is the default value of None, future
          methods will attempt to get credentials from the default credentials.

    Returns:
      A pair event, failed where event is an Event object that has been inserted
          or updated and failed is a boolean indicating failure (or lack of).

    Raises:
      MissingUID in the case that there is no UID in the iCal event
    """
    uid = ical_event.get('uid', None)
    if uid is None:
      raise MissingUID(ical_event)
    # convert from type icalendar.prop.vText to unicode
    uid = unicode(uid)

    event_data = {}
    summary = ical_event.get('summary', None)
    if not summary:
      summary = '(No Title)'
    # convert from type icalendar.prop.vText to unicode
    event_data['summary'] = unicode(summary)

    description, location = ConvertedDescription(ical_event)
    event_data['description'] = description
    event_data['location'] = location

    event_data['start'] = TimeKeyword.from_ical_event(ical_event, 'dtstart')
    event_data['end'] = TimeKeyword.from_ical_event(ical_event, 'dtend')

    event = ndb.Key(cls, uid).get()
    if event is not None:
      changed = False
      for attr, value in event_data.iteritems():
        if getattr(event, attr) != value:
          setattr(event, attr, value)
          logging.info('{attr} changed for {uid}'.format(attr=attr, uid=uid))
          changed = True

      if current_user not in event.attendees:  # pylint:disable-msg=E1103
        event.attendees.append(current_user)  # pylint:disable-msg=E1103
        logging.info('attendees changed for {uid}'.format(uid=uid))
        changed = True

      success = True
      if changed:
        # pylint:disable-msg=E1103
        success = event.update(credentials=credentials)
      return event, not success
    else:
      # pylint:disable-msg=W0142
      event = cls(key=ndb.Key(cls, uid), attendees=[current_user], **event_data)
      success = event.insert(credentials=credentials)
      return event, not success

  @ndb.ComputedProperty
  def end_date(self):  # pylint:disable-msg=C0103
    """Derived property that turns end into a date string."""
    end_datetime = self.end.to_datetime()
    end_date = end_datetime.date()
    return end_date.strftime('%Y-%m-%d')

  def attendee_emails(self):  # pylint:disable-msg=C0103
    """Returns a list of dictionaries corresponding to attendee emails."""
    return [{'email': attendee.email()} for attendee in self.attendees]

  def as_dict(self):  # pylint:disable-msg=C0103
    """Returns the Event as a dictionary corresponding to the API spec.

    Returns:
      A dictionary to be used with the API client library representing all
          the data in the model object.
    """
    return {'start': self.start.as_dict(),
            'end': self.end.as_dict(),
            'summary': self.summary,
            'location': self.location,
            'description': self.description,
            'id': self.gcal_edit,
            'sequence': self.sequence,
            'attendees': self.attendee_emails()}

  def __repr__(self):
    return 'Event(name={})'.format(self.key.id())


class UserCal(ndb.Model):  # pylint:disable-msg=R0903
  """Holds data for a calendar event (including shared owners)."""
  # pylint:disable-msg=E1101
  owner = ndb.UserProperty(required=True)
  calendars = ndb.StringProperty(repeated=True)
  update_intervals = ndb.IntegerProperty(repeated=True)
  upcoming = ndb.StringProperty(repeated=True)

  def put(self):  # pylint:disable-msg=C0103
    """Customized put function that first sorts the list in upcoming."""
    self.upcoming = sorted(set(self.upcoming))
    super(UserCal, self).put()

  def __repr__(self):
    return 'UserCal(owner={owner},name={name})'.format(owner=self.owner.email(),
                                                       name=self.key.id())

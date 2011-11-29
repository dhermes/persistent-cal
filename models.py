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


"""Model classes for persistent-cal"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


from google.appengine.ext import db


class Event(db.Model):
  """Holds data for a calendar event (including shared attendees)"""
  who = db.StringListProperty(required=True)  # hold owner ids as strings
  event_data = db.TextProperty(required=True)  # python dict as simplejson
  gcal_edit = db.StringProperty(required=True)

  def __repr__(self):
    return 'Event(name=%s)' % self.key().name()


class UserCal(db.Model):
  """Holds data for a calendar event (including shared owners)"""
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

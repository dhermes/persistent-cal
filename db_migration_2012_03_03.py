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


"""DB migration for Calendar v2 to v3 upgrade on 2012-03-03.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from db_migration_2012_03_03 import UpdateEvents
s~persistent-cal> UpdateEvents()

Note:
  We are adding a gcal_edit_old entry, because the gcal_edit entry will
  be removed eventually

    gcal_edit_old = db.StringProperty()

  for the purposes of this migration.
"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# App specific libraries
from models import Event


def UpdateEvents():
  events = Event.all()
  for event in events:
    event.gcal_edit_old = event.gcal_edit
    event.put()

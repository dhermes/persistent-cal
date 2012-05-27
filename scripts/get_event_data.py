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


"""Gets all events from GCal."""


# General libraries
import json
import os

# Third-party libraries

# App specific libraries
from library import CALENDAR_ID
from library import InitService
from models import Event


os.environ['HTTP_HOST'] = 'persistent-cal.appspot.com'


def main():
  gcal_edits = []
  for event in Event.all():
    gcal_edits.append(event.gcal_edit)

  service = InitService()
  events = {}
  for gcal_edit in gcal_edits:
    event = service.events().get(calendarId=CALENDAR_ID,
                                 eventId=gcal_edit).execute()
    events[gcal_edit] = event

  with open('gcal_events.json', 'w') as fh:
    json.dump(events, fh)

  return events


if __name__ == '__main__':
  main()

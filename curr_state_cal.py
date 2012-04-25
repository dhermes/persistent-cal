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


"""Debugging tool to get current state of main calendar."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import json

# Third-party libraries
import gdata.calendar.client
import gdata.gauth

# App specific libraries
# from library import InitGCAL
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET
from secret_key import TOKEN
from secret_key import TOKEN_SECRET


def main():
  """Processes main calendar event feed and writes some event data to a file.

  get_calendar_event_feed uses a default desired_class of
  `gdata.calendar.data.CalendarEventFeed`
  hence the get_feed request uses this class to convert the response

  In order to retrieve the full feed, the total_results field is analyzed
  from the first request and a new request is sent with max-results set in
  the query to the total number of events.

  The CalendarEventFeed class has an event field which holds a list of
  CalendarEventEntry classes. Each CalendarEventEntry class has a when field
  and a who field (which we use) and a get_edit_link member function which we
  also use.

  In the result, we use the href from the edit link as a key for each event and
  write the start and end times from the when field as well as all the email
  addresses of the attendees from the who field to a dictionary. This dictionary
  is then written to a file as serialized JSON.

  raises Exception if an edit link is encountered more than once
  """
  # TODO(dhermes) fix the import issue for the authorized client
  # InitGCAL won't import since library.py has app engine imports
  # GCAL = InitGCAL()
  gcal = gdata.calendar.client.CalendarClient(source='persistent-cal')
  auth_token = gdata.gauth.OAuthHmacToken(consumer_key=CONSUMER_KEY,
                                          consumer_secret=CONSUMER_SECRET,
                                          token=TOKEN,
                                          token_secret=TOKEN_SECRET,
                                          auth_state=3)
  gcal.auth_token = auth_token
  uri = ('https://www.google.com/calendar/feeds/'
         'vhoam1gb7uqqoqevu91liidi80%40group.calendar.google.com/private/full')

  feed = gcal.get_calendar_event_feed(uri=uri)
  total_results = int(feed.total_results.text)  # TODO(dhermes) catch error here
  if total_results > 25:
    uri = '%s?max-results=%s' % (uri, total_results)
    feed = gcal.get_calendar_event_feed(uri=uri)

  result = {}
  for event in feed.entry:
    # each event is [CalendarEventEntry]
    when = event.when  # when is [When]
    curr_starts = [t.start for t in when]  # [string]
    curr_ends = [t.end for t in when]  # [string]
    # who is [gdata.data.Who]
    who = [v.email for v in event.who]
    # each v.email is string
    gcal_edit = event.get_edit_link().href  # string
    if gcal_edit in result:
      raise Exception('Hmmmmmmm, duplicate')
    else:
      result[gcal_edit] = {'starts': curr_starts,
                           'ends': curr_ends,
                           'who': who}

  with open('curr_state_cal.json', 'wb') as fh:
    json.dump(result, fh)

if __name__ == '__main__':
  main()

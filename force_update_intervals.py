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


"""Tool for kicking off an update at a specific interval.

Intended to be run through the remote API:

remote_api_shell.py -s persistent-cal.appspot.com

s~persistent-cal> import sys
s~persistent-cal> sys.path.append('/path/to/persistent-cal')
s~persistent-cal> from force_update_intervals import ForceUpdate
s~persistent-cal> now_intervals = [3, 4]  # integers between 0 and 55 inclusive
s~persistent-cal> ForceUpdate(now_intervals)

Note:
  This is intended to be used when an update or set of updates fail and a bug
  is fixed that allows those updates to work.
"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# App specific libraries
from library import InitCredentials
from library import UpdateUserSubscriptions
from models import UserCal


CREDENTIALS = InitCredentials()


def ForceUpdate(now_intervals):
  """Forces an update outside of a cron job for a list of update intervals."""
  all_users = UserCal.all()  # pylint:disable-msg=E1101
  for user_cal in all_users:
    for now_interval in now_intervals:
      if now_interval in user_cal.update_intervals:
        UpdateUserSubscriptions(user_cal.calendars, user_cal,
                                CREDENTIALS, defer_now=True)
        break

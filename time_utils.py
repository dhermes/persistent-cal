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


"""Time utility library for persistent-cal with no App Engine depencies.

Provides time related parsing and conversion functions.
"""


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import datetime


def ConvertToInterval(timestamp):
  """Converts a datetime timestamp to a time interval for a cron job.

  Args:
    timestamp: a datetime.datetime object

  Returns:
    A value between 0 and 55 corresponding to the interval the timestamp
    falls in. In this calculation, 12am on Monday is interval 0 and each
    interval lasts 3 hours.
  """
  # In datetime, Monday is day 0, sunday is day 6
  # Since 8 intervals in a day, multiply by 8. Round up hours.
  interval = 8*timestamp.weekday() + timestamp.hour/3 + 1

  # If we are exactly on an hour that is a multiple of three
  # we do not wish to round up since floor(x) == ceil(x), contrary
  # to all other cases where ceil(x) == floor(x) + 1
  relative_seconds = sum([3600*(timestamp.hour % 3 == 0),
                          60*timestamp.minute,
                          timestamp.second,
                          timestamp.microsecond/1000.0])
  if relative_seconds < 300:  # under 5 minutes past schedule
    interval -= 1

  return interval % 56


def FormatTime(time_value):
  """Takes a datetime object and returns a formatted time stamp.

  Args:
    time_value: a datetime.datetime or datetime.date object

  Returns:
    A string value of the datetime object formatted according to the values
        set in time_parse below
  """
  # Fails if not datetime.datetime or datetime.date

  # strftime('%Y-%m-%dT%H:%M:%S.000Z') for datetime
  # strftime('%Y-%m-%d') for date

  # Default TZ is UTC/GMT (as is TZ in GCal)
  time_parse = '%Y-%m-%d'
  if isinstance(time_value, datetime.datetime):
    time_parse += 'T%H:%M:%S.000Z'
    return time_value.strftime(time_parse)
  elif isinstance(time_value, datetime.date):
    return time_value.strftime(time_parse)

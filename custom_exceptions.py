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


"""Exceptions module for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


class Error(Exception):
  """Base error class for library functions."""


class AttendeesNotUpdated(Error):
  """Error corresponding to an unexpected value of models.Event.attendees."""


class BadInterval(Error):
  """Error corresponding to an unanticipated number of update intervals."""


class CredentialsLoadError(Error):
  """Error when credentials are not loaded correctly from a specified file."""


class MissingUID(Error):
  """Error corresponding to missing UID in an event."""


class UnexpectedDescription(Error):
  """Error corresponding to an unexpected event description."""
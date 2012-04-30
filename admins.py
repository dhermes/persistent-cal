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


"""Admin list to be used as constants within the application."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# http://code.google.com/appengine/docs/python/mail/emailmessagefields.html
ADMIN_LIST = [('Robert Admin', 'admin@example.com')]
ADMIN_LIST_AS_STR = ['%s <%s>' % (name, email) for name, email in ADMIN_LIST]
ADMINS_TO = ', '.join(ADMIN_LIST_AS_STR)

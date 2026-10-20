#!/usr/keio/Anaconda3-2025.12-2/bin/python

from wsgiref.handlers import CGIHandler
import os
os.environ['SCRIPT_NAME'] = \
    os.environ['SCRIPT_NAME'].removesuffix('/index.cgi')

from app import app

CGIHandler().run(app)

#!/usr/bin/python
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#
# Copyright 2007 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import os
import re
import sha
import shutil
import time
import urllib

import pkg.fmri as fmri
import pkg.version as version
import pkg.server.catalog as catalog

class SPackage(object):
        """An SPackage is the server's representation of a versioned package
        sequence."""

        def __init__(self, cfg, fmri):
                self.fmri = fmri
                self.cfg = cfg
                self.versions = ()

                authority, pkg_name, version = self.fmri.tuple()

                self.dir = "%s/%s" % (self.cfg.pkg_root,
                    urllib.quote(pkg_name, ""))

                # Bulk state represents whether the server knows of any version
                # of this package.  It is false for a new package.
                self.bulk_state = True
                try:
                        os.stat(self.dir)
                except:
                        self.bulk_state = False

                return

        def load(self):
                """Iterate through directory and build version list.  Each entry
                is a separate version of the package."""
                if not self.bulk_state:
                        return

                for e in os.listdir(self.dir):
                        v = version.Version(e)
                        self.versions.append(v)

                self.versions.sort()
                return

        def can_open_version(self, version):
                # validate that this version can be opened
                #   if we specified no release, fail
                #   if we specified a release without branch, open next branch
                #   if we specified a release with branch major, open same
                #     branch minor
                #   if we specified a release with branch major and minor, use
                #   as specified
                # we should disallow new package creation, if so flagged

                return True

        def update(self, trans):
                if not self.bulk_state:
                        os.makedirs(self.dir)

                (authority, name, version) = self.fmri.tuple()

                # mv manifest to pkg_name / version
                os.rename("%s/manifest" % trans.dir, "%s/%s" % (self.dir, version))

                # mv each file to file_root
                for f in os.listdir(trans.dir):
                        os.rename("%s/%s" % (trans.dir, f),
                            "%s/%s" % (self.cfg.file_root, f))

                # add entry to catalog

                return

        def get_state(self, version):
                return 0;

        def get_manifest(self, version):
                return

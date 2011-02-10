#!/usr/bin/python
# Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009 Python
# Software Foundation; All Rights Reserved
#
# Copyright (c) 2010, 2011, Oracle and/or its affiliates. All rights reserved.


"""A version of ModuleFinder which limits the depth of exploration for loaded
modules and discovers where a module might be loaded instead of determining
which path contains a module to be loaded."""

import modulefinder
import os
import sys

python_path = "PYTHONPATH"

class ModuleInfo(object):
        """This class contains information about from where a python module
        might be loaded."""

        def __init__(self, name, dirs, builtin=False):
                """Build a ModuleInfo object.

                The 'name' parameter is the name of the module.

                The 'dirs' parameter is the list of directories where the module
                might be found.

                The 'builtin' parameter sets whether the module is a python
                builtin (like sys)."""

                self.name = name
                self.builtin = builtin
                self.suffixes = [".py", ".pyc", ".pyo", "/__init__.py"]
                self.dirs = sorted(dirs)

        def make_package(self):
                """Declare that this module is a package."""

                if self.dirs:
                        self.suffixes = ["/__init__.py"]
                else:
                        self.suffixes = []

        def get_package_dirs(self):
                """Get the directories where this package might be defined."""

                return [os.path.join(p, self.name) for p in self.dirs]

        def get_file_names(self):
                """Return all the file names under which this module might be
                found."""

                return ["%s%s" % (self.name, suf) for suf in self.suffixes]

        def __str__(self):
                return "name:%s suffixes:%s dirs:%s" % (self.name,
                    " ".join(self.suffixes), len(self.dirs))

class DepthLimitedModuleFinder(modulefinder.ModuleFinder):

        def __init__(self, proto_dir, *args, **kwargs):
                """Produce a module finder that ignores PYTHONPATH and only
                reports the direct imports of a module."""

                # Check to see whether a python path has been set.
                if python_path in os.environ:
                        py_path = [
                            os.path.normpath(fp)
                            for fp in os.environ[python_path].split(os.pathsep)
                        ]
                else:
                        py_path = []

                # Remove any paths that start with the defined python paths.
                new_path = [
                    fp
                    for fp in sys.path
                    if not self.startswith_path(fp, py_path)
                ]

                # Map the standard system paths into the proto area.
                new_path = [
                    os.path.join(proto_dir, fp.lstrip("/"))
                    for fp in new_path
                ]

                modulefinder.ModuleFinder.__init__(self, path=new_path,
                    *args, **kwargs)
                self.proto_dir = proto_dir

        @staticmethod
        def startswith_path(path, lst):
                for l in lst:
                        if path.startswith(l):
                                return True
                return False

        def run_script(self, pathname):
                """Find all the modules the module at pathname directly
                imports."""

                fp = open(pathname, "r")
                return self.load_module('__main__', fp, pathname)

        def load_module(self, fqname, fp, pathname):
                """This code has been slightly modified from the function of
                the parent class. Specifically, it checks the current depth
                of the loading and halts if it exceeds the depth that was given
                to run_script."""

                self.msgin(2, "load_module", fqname, fp and "fp", pathname)
                co = compile(fp.read()+'\n', pathname, 'exec')
                m = self.add_module(fqname)
                m.__file__ = pathname
                res = []
                if co:
                        if self.replace_paths:
                                co = self.replace_paths_in_code(co)
                        m.__code__ = co
                        try:
                                res.extend(self.scan_code(co, m))
                        except ImportError, msg:
                                self.msg(2, "ImportError:", str(msg), fqname,
                                    pathname)
                                self._add_badmodule(fqname, m)

                self.msgout(2, "load_module ->", m)
                return res

        def scan_code(self, co, m):
                """Scan the code looking for import statements."""

                res = []
                code = co.co_code
                if sys.version_info >= (2, 5):
                        scanner = self.scan_opcodes_25
                else:
                        scanner = self.scan_opcodes
                for what, args in scanner(co):
                        if what == "store":
                                name, = args
                                m.globalnames[name] = 1
                        elif what in ("import", "absolute_import"):
                                fromlist, name = args
                                have_star = 0
                                if fromlist is not None:
                                        if "*" in fromlist:
                                                have_star = 1
                                        fromlist = [
                                            f for f in fromlist if f != "*"
                                        ]
                                if what == "absolute_import": level = 0
                                else: level = -1
                                res.extend(self._safe_import_hook(name, m,
                                    fromlist, level=level))
                        elif what == "relative_import":
                                level, fromlist, name = args
                                if name:
                                        res.extend(self._safe_import_hook(name,
                                            m, fromlist, level=level))
                                else:
                                        parent = self.determine_parent(m,
                                            level=level)
                                        res.extend(self._safe_import_hook(
                                            parent.__name__, None, fromlist,
                                            level=0))
                        else:
                                # We don't expect anything else from the
                                # generator.
                                raise RuntimeError(what)

                for c in co.co_consts:
                        if isinstance(c, type(co)):
                                res.extend(self.scan_code(c, m))
                return res


        def _safe_import_hook(self, name, caller, fromlist, level=-1):
                """Wrapper for self.import_hook() that won't raise ImportError.
                """

                res = []
                if name in self.badmodules:
                        self._add_badmodule(name, caller)
                        return []
                try:
                        res.extend(self.import_hook(name, caller, level=level))
                except ImportError, msg:
                        self.msg(2, "ImportError:", str(msg))
                        self._add_badmodule(name, caller)
                else:
                        if fromlist:
                                for sub in fromlist:
                                        if sub in self.badmodules:
                                                self._add_badmodule(sub, caller)
                                                continue
                                        res.extend(self.import_hook(name,
                                            caller, [sub], level=level))
                return res

        def import_hook(self, name, caller=None, fromlist=None, level=-1):
                """Find all the modules that importing name will import."""

                self.msg(3, "import_hook", name, caller, fromlist, level)
                parent = self.determine_parent(caller, level=level)
                q, tail = self.find_head_package(parent, name)
                if not tail:
                        # If q is a builtin module, don't report it because it
                        # doesn't live in the normal module space and it's part
                        # of python itself, which is handled by a different
                        # kind of dependency.
                        if isinstance(q, ModuleInfo) and q.builtin:
                                return []
                        elif isinstance(q, modulefinder.Module):
                                name = q.__name__
                                path = q.__path__
                                # some Module objects don't get a path
                                if not path:
                                        if name in sys.builtin_module_names or \
                                            name == "__future__":
                                                return [ModuleInfo(name, [],
                                                    builtin=True)]
                                        else:
                                                return [ModuleInfo(name, [])]
                                return [ModuleInfo(name, path)]
                        else:
                                return [q]
                res = self.load_tail(name, q, tail)
                q.make_package()
                res.append(q)
                return res

        def import_module(self, partname, fqname, parent):
                """Find where this module lives relative to its parent."""

                parent_dirs = None
                self.msgin(3, "import_module", partname, fqname, parent)
                try:
                        m = self.modules[fqname]
                except KeyError:
                        pass
                else:
                        self.msgout(3, "import_module ->", m)
                        return m
                if fqname in self.badmodules:
                        self.msgout(3, "import_module -> None")
                        return None
                if parent:
                        if not parent.dirs:
                                self.msgout(3, "import_module -> None")
                                return None
                        else:
                                parent_dirs = parent.get_package_dirs()
                try:
                        mod = self.find_module(partname, parent_dirs, parent)
                except ImportError:
                        self.msgout(3, "import_module ->", None)
                        return None
                return mod

        def find_module(self, name, path, parent=None):
                """Calculate the potential paths on the file system where the
                module could be found."""

                if not path:
                    if name in sys.builtin_module_names or name == "__future__":
                            return ModuleInfo(name, [], builtin=True)
                    path = self.path
                return ModuleInfo(name, path)

        def load_tail(self, name, q, tail):
                """Determine where each component of a multilevel import would
                be found on the file system."""

                self.msgin(4, "load_tail", q, tail)
                m = q
                res = []
                while tail:
                        i = tail.find('.')
                        if i < 0: i = len(tail)
                        head, tail = tail[:i], tail[i+1:]
                        new_name = "%s.%s" % (name, head)
                        r = self.import_module(head, new_name, q)
                        res.append(r)
                        name = new_name
                # All but the last module found must be packages because they
                # contained other packages.
                for i in range(0, len(res) - 1):
                        res[i].make_package()
                self.msgout(4, "load_tail ->", m)
                return res

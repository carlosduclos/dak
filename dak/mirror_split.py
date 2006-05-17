#!/usr/bin/env python

# Prepare and maintain partial trees by architecture
# Copyright (C) 2004, 2006  Daniel Silverstone <dsilvers@digital-scurf.org>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


###############################################################################
## <kinnison> So Martin, do you have a quote for me yet?
## <tbm> Make something damned stupid up and attribute it to me, that's okay
###############################################################################

import sys
import apt_pkg

from stat import S_ISDIR, S_ISLNK, S_ISREG
import os
import cPickle

import dak.lib.utils as utils

## Master path is the main repository
#MASTER_PATH = "/org/ftp.debian.org/scratch/dsilvers/master"

MASTER_PATH = "***Configure Mirror-Split::FTPPath Please***"
TREE_ROOT = "***Configure Mirror-Split::TreeRootPath Please***"
TREE_DB_ROOT = "***Configure Mirror-Split::TreeDatabasePath Please***"
trees = []

Cnf = None

###############################################################################
# A MirrorSplitTarget is a representation of a target. It is a set of archs, a path
# and whether or not the target includes source.
##################

class MirrorSplitTarget:
    def __init__(self, name, archs, source):
        self.name = name
        self.root = "%s/%s" % (TREE_ROOT,name)
        self.archs = archs.split(",")
        self.source = source
        self.dbpath = "%s/%s.db" % (TREE_DB_ROOT,name)
        self.db = MirrorSplitDB()
        if os.path.exists( self.dbpath ):
            self.db.load_from_file( self.dbpath )

    ## Save the db back to disk
    def save_db(self):
        self.db.save_to_file( self.dbpath )

    ## Returns true if it's a poolish match
    def poolish_match(self, path):
        for a in self.archs:
            if path.endswith( "_%s.deb" % (a) ):
                return 1
            if path.endswith( "_%s.udeb" % (a) ):
                return 1
        if self.source:
            if (path.endswith( ".tar.gz" ) or
                path.endswith( ".diff.gz" ) or
                path.endswith( ".dsc" )):
                return 1
        return 0

    ## Returns false if it's a badmatch distswise
    def distish_match(self,path):
        for a in self.archs:
            if path.endswith("/Contents-%s.gz" % (a)):
                return 1
            if path.find("/binary-%s/" % (a)) != -1:
                return 1
            if path.find("/installer-%s/" % (a)) != -1:
                return 1
        if path.find("/source/") != -1:
            if self.source:
                return 1
            else:
                return 0
        if path.find("/Contents-") != -1:
            return 0
        if path.find("/binary-") != -1:
            return 0
        if path.find("/installer-") != -1:
            return 0
        return 1
    
##############################################################################
# The applicable function is basically a predicate. Given a path and a
# target object its job is to decide if the path conforms for the
# target and thus is wanted.
#
# 'verbatim' is a list of files which are copied regardless
# it should be loaded from a config file eventually
##################

verbatim = [
    ]

verbprefix = [
    "/tools/",
    "/README",
    "/doc/"
    ]

def applicable(path, target):
    if path.startswith("/pool/"):
        return target.poolish_match(path)
    if (path.startswith("/dists/") or
        path.startswith("/project/experimental/")):
        return target.distish_match(path)
    if path in verbatim:
        return 1
    for prefix in verbprefix:
        if path.startswith(prefix):
            return 1
    return 0


##############################################################################
# A MirrorSplitDir is a representation of a tree.
#   It distinguishes files dirs and links
# Dirs are dicts of (name, MirrorSplitDir)
# Files are dicts of (name, inode)
# Links are dicts of (name, target)
##############

class MirrorSplitDir:
    def __init__(self):
        self.dirs = {}
        self.files = {}
        self.links = {}

##############################################################################
# A MirrorSplitDB is a container for a MirrorSplitDir...
##############

class MirrorSplitDB:
    ## Initialise a MirrorSplitDB as containing nothing
    def __init__(self):
        self.root = MirrorSplitDir()

    def _internal_recurse(self, path):
        bdir = MirrorSplitDir()
        dl = os.listdir( path )
        dl.sort()
        dirs = []
        for ln in dl:
            lnl = os.lstat( "%s/%s" % (path, ln) )
            if S_ISDIR(lnl[0]):
                dirs.append(ln)
            elif S_ISLNK(lnl[0]):
                bdir.links[ln] = os.readlink( "%s/%s" % (path, ln) )
            elif S_ISREG(lnl[0]):
                bdir.files[ln] = lnl[1]
            else:
                utils.fubar( "Confused by %s/%s -- not a dir, link or file" %
                            ( path, ln ) )
        for d in dirs:
            bdir.dirs[d] = self._internal_recurse( "%s/%s" % (path,d) )

        return bdir

    ## Recurse through a given path, setting the sequence accordingly
    def init_from_dir(self, dirp):
        self.root = self._internal_recurse( dirp )

    ## Load this MirrorSplitDB from file
    def load_from_file(self, fname):
        f = open(fname, "r")
        self.root = cPickle.load(f)
        f.close()

    ## Save this MirrorSplitDB to a file
    def save_to_file(self, fname):
        f = open(fname, "w")
        cPickle.dump( self.root, f, 1 )
        f.close()

        
##############################################################################
# Helper functions for the tree syncing...
##################

def _pth(a,b):
    return "%s/%s" % (a,b)

def do_mkdir(targ,path):
    if not os.path.exists( _pth(targ.root, path) ):
        os.makedirs( _pth(targ.root, path) )

def do_mkdir_f(targ,path):
    do_mkdir(targ, os.path.dirname(path))

def do_link(targ,path):
    do_mkdir_f(targ,path)
    os.link( _pth(MASTER_PATH, path),
             _pth(targ.root, path))

def do_symlink(targ,path,link):
    do_mkdir_f(targ,path)
    os.symlink( link, _pth(targ.root, path) )

def do_unlink(targ,path):
    os.unlink( _pth(targ.root, path) )

def do_unlink_dir(targ,path):
    os.system( "rm -Rf '%s'" % _pth(targ.root, path) )

##############################################################################
# Reconciling a target with the sourcedb
################

def _internal_reconcile( path, srcdir, targdir, targ ):
    # Remove any links in targdir which aren't in srcdir
    # Or which aren't applicable
    rm = []
    for k in targdir.links.keys():
        if applicable( _pth(path, k), targ ):
            if not srcdir.links.has_key(k):
                rm.append(k)
        else:
            rm.append(k)
    for k in rm:
        #print "-L-", _pth(path,k)
        do_unlink(targ, _pth(path,k))
        del targdir.links[k]
    
    # Remove any files in targdir which aren't in srcdir
    # Or which aren't applicable
    rm = []
    for k in targdir.files.keys():
        if applicable( _pth(path, k), targ ):
            if not srcdir.files.has_key(k):
                rm.append(k)
        else:
            rm.append(k)
    for k in rm:
        #print "-F-", _pth(path,k)
        do_unlink(targ, _pth(path,k))
        del targdir.files[k]

    # Remove any dirs in targdir which aren't in srcdir
    rm = []
    for k in targdir.dirs.keys():
        if not srcdir.dirs.has_key(k):
            rm.append(k)
    for k in rm:
        #print "-D-", _pth(path,k)
        do_unlink_dir(targ, _pth(path,k))
        del targdir.dirs[k]

    # Add/update files
    for k in srcdir.files.keys():
        if applicable( _pth(path,k), targ ):
            if not targdir.files.has_key(k):
                #print "+F+", _pth(path,k)
                do_link( targ, _pth(path,k) )
                targdir.files[k] = srcdir.files[k]
            else:
                if targdir.files[k] != srcdir.files[k]:
                    #print "*F*", _pth(path,k)
                    do_unlink( targ, _pth(path,k) )
                    do_link( targ, _pth(path,k) )
                    targdir.files[k] = srcdir.files[k]

    # Add/update links
    for k in srcdir.links.keys():
        if applicable( _pth(path,k), targ ):
            if not targdir.links.has_key(k):
                targdir.links[k] = srcdir.links[k]; 
                #print "+L+",_pth(path,k), "->", srcdir.links[k]
                do_symlink( targ, _pth(path,k), targdir.links[k] )
            else:
                if targdir.links[k] != srcdir.links[k]:
                    do_unlink( targ, _pth(path,k) )
                    targdir.links[k] = srcdir.links[k]
                    #print "*L*", _pth(path,k), "to ->", srcdir.links[k]
                    do_symlink( targ, _pth(path,k), targdir.links[k] )

    # Do dirs
    for k in srcdir.dirs.keys():
        if not targdir.dirs.has_key(k):
            targdir.dirs[k] = MirrorSplitDir()
            #print "+D+", _pth(path,k)
        _internal_reconcile( _pth(path,k), srcdir.dirs[k],
                             targdir.dirs[k], targ )


def reconcile_target_db( src, targ ):
    _internal_reconcile( "", src.root, targ.db.root, targ )

###############################################################################

def load_config():
    global MASTER_PATH
    global TREE_ROOT
    global TREE_DB_ROOT
    global trees

    MASTER_PATH = Cnf["Mirror-Split::FTPPath"]
    TREE_ROOT = Cnf["Mirror-Split::TreeRootPath"]
    TREE_DB_ROOT = Cnf["Mirror-Split::TreeDatabasePath"]
    
    for a in Cnf.ValueList("Mirror-Split::BasicTrees"):
        trees.append( MirrorSplitTarget( a, "%s,all" % a, 1 ) )

    for n in Cnf.SubTree("Mirror-Split::CombinationTrees").List():
        archs = Cnf.ValueList("Mirror-Split::CombinationTrees::%s" % n)
        source = 0
        if "source" in archs:
            source = 1
            archs.remove("source")
        archs = ",".join(archs)
        trees.append( MirrorSplitTarget( n, archs, source ) )

def do_list ():
    print "Master path",MASTER_PATH
    print "Trees at",TREE_ROOT
    print "DBs at",TREE_DB_ROOT

    for tree in trees:
        print tree.name,"contains",", ".join(tree.archs),
        if tree.source:
            print " [source]"
        else:
            print ""
        
def do_help ():
    print """Usage: dak mirror-split [OPTIONS]
Generate hardlink trees of certain architectures

  -h, --help                 show this help and exit
  -l, --list                 list the configuration and exit
"""


def main ():
    global Cnf

    Cnf = utils.get_conf()

    Arguments = [('h',"help","Mirror-Split::Options::Help"),
                 ('l',"list","Mirror-Split::Options::List"),
                 ]

    arguments = apt_pkg.ParseCommandLine(Cnf,Arguments,sys.argv)
    Cnf["Mirror-Split::Options::cake"] = ""
    Options = Cnf.SubTree("Mirror-Split::Options")

    print "Loading configuration..."
    load_config()
    print "Loaded."

    if Options.has_key("Help"):
        do_help()
        return
    if Options.has_key("List"):
        do_list()
        return
    

    src = MirrorSplitDB()
    print "Scanning", MASTER_PATH
    src.init_from_dir(MASTER_PATH)
    print "Scanned"

    for tree in trees:
        print "Reconciling tree:",tree.name
        reconcile_target_db( src, tree )
        print "Saving updated DB...",
        tree.save_db()
        print "Done"
    
##############################################################################

if __name__ == '__main__':
    main()
#!/usr/bin/env python

import re, sys, os
import datetime
import cycle_time
from batchproc import batchproc

class HousekeepingError( Exception ):
    """
    Attributes:
        message - what the problem is. 
    """
    def __init__( self, msg ):
        self.msg = msg
    def __str__( self ):
        return repr(self.msg)

class NonIdenticalTargetError( HousekeepingError ):
    pass

class OperationFailedError( HousekeepingError ):
    pass

class config_line:
    """
        Process a single cylc housekeeping config line. Matched items
        are batched and members of each batch are processed in parallel
        (in the sense of parallel unix processes). One batch must finish
        before the next is processed.
    """
    legal_ops = [ 'copy', 'move', 'delete' ]
    def __init__( self, source, match, oper, ctime, offset, dest=None, verbose=False, cheap=False ):
        self.source = source
        self.match = match
        self.ctime = ctime
        self.offset = offset
        self.opern = oper 
        self.destn = dest
        self.verbose = verbose
        self.cheap = cheap

        # interpolate SIMPLE environment variables ($foo, ${foo}) into paths
        self.source = os.path.expandvars( self.source )
        if dest:
            self.destn = os.path.expandvars( self.destn )

        # check the validity of the match pattern
        if re.search( '\(\\\d\{10\}\)', self.match ) or \
                re.search( '\(\\\d\{8\}\)', self.match ) and \
                re.search( '\(\\\d\{2\}\)', self.match ):
            pass
        else:
            # putting match in the raise results in it being mangled
            # slightly ( '\d' --> '\\d' ).
            print >> sys.stderr, 'ERROR: ', self.match
            raise HousekeepingError, 'Bad pattern'

        # check the validity of the base cycle time
        if not cycle_time.is_valid( self.ctime ):
            raise HousekeepingError, 'Bad cycle time: ' + self.ctime

        # check the validity of the offset
        try:
            int( self.offset )
        except ValueError:
            raise HousekeepingError, 'Cycle time offset must be integer: ' + self.offset

        # check the validity of the source directory
        if not os.path.isdir( self.source ):
            raise HousekeepingError, 'Source directory not found: ' + self.source
 
        # check the validity of the requested housekeeping operation
        if self.opern not in self.__class__.legal_ops:
            raise HousekeepingError, "Illegal operation: " + self.opern

    def action( self, batchsize ):
        src_entries = 0
        matched = 0
        not_matched = 0
        total = 0
        actioned = 0
        print "________________________________________________________________________"
        print "SOURCE:", self.source
        if self.destn:
            print "TARGET:", self.destn
        print "MATCH :", self.match
        print "ACTION:", self.opern
        print "CUTOFF:", self.ctime, '-', self.offset, '=', cycle_time.decrement( self.ctime, self.offset )
        batch = batchproc( batchsize )
        for entry in os.listdir( self.source ):
            src_entries += 1
            entrypath = os.path.join( self.source, entry )
            item = hkitem( entrypath, self.match, self.opern, self.ctime, self.offset, self.destn, self.verbose, self.cheap )
            if not item.matches():
                not_matched += 1
                continue
            matched += 1
            item.interpolate_destination()
            actioned += batch.add_or_process( item )
        actioned += batch.process()
 
        print 'MATCHED :', str(matched) + '/' + str(src_entries)
        print 'ACTIONED:', str(actioned) + '/' + str(matched)

class config_file:
    """
        Process a cylc housekeeping config file, line by line.
    """
    def __init__( self, file, ctime, excpt=None, only=None, verbose=False, cheap=False):
        self.lines = []
        if not os.path.isfile( file ):
            raise HousekeepingError, "file not found: " + file 

        print "Parsing housekeeping config file", os.path.abspath( file )
        sys.stdout.flush()

        FILE = open( file, 'r' )
        lines = FILE.readlines()
        FILE.close()

        for line in lines:
            # strip trailing newlines
            line = line.rstrip( '\n' )
            # omit blank lines
            if re.match( '^\s*$', line ):
                continue
            # omit full line comments
            if re.match( '^\s*#', line ):
                continue
            # strip trailing comments
            line = re.sub( '#.*$', '', line )

            # defined environment variables
            m = re.match( '(\w+)=(.*)', line )
            if m:
                varname=m.group(1)
                varvalue=m.group(2)
                os.environ[varname] = os.path.expandvars( varvalue )
                if verbose:
                    print 'Defining variable: ', varname, '=', varvalue
                continue

            # parse line
            tokens = line.split()
            destination = ''
            if len( tokens ) == 5:
                source, match, operation, offset, destination = tokens
            elif len( tokens ) == 4:
                source, match, operation, offset = tokens
            else:
                raise HousekeepingError, "illegal config line:\n  " + line

            skip = False

            if excpt:
                skip = False
                # if line matches any of the given patterns, skip it
                for pattern in re.split( r', *| +', excpt ):
                    if re.search( pattern, line ):
                        skip = True
                        break
            if only:
                skip = True
                # if line does not match any of the given patterns, skip it
                for pattern in re.split( r', *| +', only ):
                    if re.search( pattern, line ):
                        skip = False
                        break
            if skip:
                print "\n   *** SKIPPING " + line
                continue

            self.lines.append( config_line( source, match, operation, ctime, offset, destination, verbose=verbose, cheap=cheap ))

    def action( self, batchsize ):
        for item in self.lines:
            item.action( batchsize )

class hkitem:
    """
        Handle processing of a single source directory entry
    """
    def __init__( self, path, pattern, operation, ctime, offset, destn, verbose=False, cheap=False ):
        # Assumes the validity of pattern has already been checked
        self.operation = operation
        self.path = path
        self.pattern = pattern
        self.ctime = ctime
        self.offset = offset
        self.destn = destn
        self.matched_ctime = None
        self.verbose = verbose
        self.cheap = cheap

    def matches( self ):
        if self.verbose:
            print "\nSource item:", self.path

        # does path match pattern
        m = re.search( self.pattern, self.path )
        if not m:
            if self.verbose:
                print " + does not match"
            return False

        if self.verbose:
            print " + MATCH"

        # extract cycle time from path
        mgrps = m.groups()
        if len(mgrps) == 1:
            self.matched_ctime = mgrps[0]
        elif len(mgrps) == 2:
            foo, bar = mgrps
            if len(foo) == 8 and len(bar) == 2:
                self.matched_ctime = foo + bar
            elif len(foo) == 2 and len(bar) == 8:
                self.matched_ctime = bar + foo
            else:
                print "WARNING: Housekeeping match problem:"
                print " + path: "+ self.path
                print " + pattern: " + self.pattern
                print " > extracted time groups:", m.groups()
                return False
        else:
            print "WARNING: Housekeeping match problem:"
            print " + path: "+ self.path
            print " + pattern: " + self.pattern
            print " > extracted time groups:", m.groups()
            return False

        # check validity of extracted cycle time
        if not cycle_time.is_valid( self.matched_ctime ):
            if self.verbose:
                print " + extracted cycle time is NOT VALID: " + self.matched_ctime
            return False
        else:
            if self.verbose:
                print " + extracted cycle time: " + self.matched_ctime

        # assume ctime is >= self.matched_ctime
        gap = cycle_time.diff_hours( self.ctime, self.matched_ctime )
        if self.verbose:
            print " + computed offset hours", gap,
        if int(gap) < int(self.offset):
            if self.verbose:
                print "- ignoring (does not make the cutoff)"
            return False
        
        if self.verbose:
            print "- ACTIONABLE (does make the cutoff)"
        return True

    def interpolate_destination( self ):
        # Interpolate cycle time components into destination if necessary.
        if self.destn:
            # destination directory may be cycle time dependent
            dest = self.destn
            dest = re.sub( 'YYYYMMDDHH', self.matched_ctime, dest )
            dest = re.sub( 'YYYYMMDD', self.matched_ctime[0:8], dest )
            dest = re.sub( 'YYYYMM', self.matched_ctime[0:6], dest )
            dest = re.sub( 'MMDD', self.matched_ctime[4:8], dest )
            dest = re.sub( 'YYYY', self.matched_ctime[0:4], dest )
            dest = re.sub( 'MM', self.matched_ctime[8:10], dest )
            dest = re.sub( 'DD', self.matched_ctime[6:8], dest )
            dest = re.sub( 'HH', self.matched_ctime[8:10], dest )
            if self.verbose and dest != self.destn:
                print " + expanded destination directory:\n  ", dest
            self.destn = dest

    def execute( self ):
        if self.operation == 'copy':
            compath = os.path.join( os.environ['CYLC_DIR'], 'util', '_hk_copy.py' ) 
        elif self.operation == 'move':
            compath = os.path.join( os.environ['CYLC_DIR'], 'util', '_hk_move.py' ) 
        elif self.operation == 'delete':
            compath = os.path.join( os.environ['CYLC_DIR'], 'util', '_hk_delete.py' ) 

        commandlist = [compath]
        # TO DO: ADD OPTION PARSER TO THE _HK COMMANDS, for -c and -v
        #if self.verbose:
        #    commandlist.append( '-v' )
        #if self.cheap:
        #    commandlist.append( '-c' )

        return commandlist + [ self.path, self.destn ]
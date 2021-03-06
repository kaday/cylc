#!/bin/bash
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2015 NIWA
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------
# Test the cylc-doc command on printing cylc URLs.
. $(dirname $0)/test_header
#-------------------------------------------------------------------------------
set_test_number 2
#-------------------------------------------------------------------------------
create_test_globalrc "" "
[documentation]
   [[files]]
      pdf user guide = ${PWD}/doc/pdf/cug-pdf.pdf
      multi-page html user guide = /home/bob/cylc/cylc.git/doc/html/multi/cug-html.html
      html index = /home/bob/cylc/cylc.git/doc/index.html
      single-page html user guide = /home/bob/cylc/cylc.git/doc/html/single/cug-html.html
   [[urls]]
      internet homepage = http://cylc.github.com/cylc/
      local index = http://localhost/cylc/index.html"
#-------------------------------------------------------------------------------
mkdir -p doc/pdf
touch doc/pdf/cug-pdf.pdf
cylc doc -s -p > stdout1.txt
cmp_ok stdout1.txt <<__END__
$PWD/doc/pdf/cug-pdf.pdf
__END__
#-------------------------------------------------------------------------------
cylc doc -s > stdout2.txt
cmp_ok stdout2.txt <<__END__
http://localhost/cylc/index.html
__END__
#-------------------------------------------------------------------------------

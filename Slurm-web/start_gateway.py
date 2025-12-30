#!/usr/bin/python3
# -*- coding: utf-8 -*-
import re
import sys
from slurmweb.exec.gateway import SlurmwebExecGateway
if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])
    sys.exit(SlurmwebExecGateway.run())
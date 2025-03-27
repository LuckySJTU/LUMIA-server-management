#!/bin/bash

for i in {1..11}
do
    echo "===node$i==="
    ssh node$i $1
    echo "============"
done

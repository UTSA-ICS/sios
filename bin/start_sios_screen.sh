#!/bin/bash

NL=`echo -ne '\015'`
SIOS_CMD="cd /opt/stack/sios; /opt/stack/sios/bin/sios-api --config-file=/etc/sios/sios-api.conf || touch \"/opt/stack/status/stack/sios-api.failure\""
SIOS_LOGFILE="/opt/stack/logs/screen/screen-sios.log"
SCREEN=$(which screen)
if [[ -n "$SCREEN" ]]; then
    SESSION=$(screen -ls | awk '/[0-9].stack/ { print $1 }')
    if [[ -n "$SESSION" ]]; then
        screen -S $SESSION -X screen -t sios bash
        screen -S $SESSION -p sios -X logfile $SIOS_LOGFILE
        screen -S $SESSION -p sios -X log on
        screen -S $SESSION -p sios -X stuff "$SIOS_CMD $NL"
    fi
fi


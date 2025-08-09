#!/bin/python3
# -*- coding: utf-8 -*-

import yaml
import argparse
import os
from datetime import datetime, timedelta
import pytz
from copy import deepcopy
import re

ANSI = {
    'reset':      '\033[0m',
    'bold':       '\033[1m',
    'dim':        '\033[2m',
    'underline':  '\033[4m',
    'blink':      '\033[5m',
    'reverse':    '\033[7m',
    'hidden':     '\033[8m',
    'fg_black':   '\033[30m',
    'fg_red':     '\033[31m',
    'fg_green':   '\033[32m',
    'fg_yellow':  '\033[33m',
    'fg_blue':    '\033[34m',
    'fg_magenta': '\033[35m',
    'fg_cyan':    '\033[36m',
    'fg_white':   '\033[37m',
    'bg_black':   '\033[40m',
    'bg_red':     '\033[41m',
    'bg_green':   '\033[42m',
    'bg_yellow':  '\033[43m',
    'bg_blue':    '\033[44m',
    'bg_magenta': '\033[45m',
    'bg_cyan':    '\033[46m',
    'bg_white':   '\033[47m',
}

TZ_ALIAS_MAP = {
    'AoE': 'Etc/GMT+12',
    'UTC': 'UTC',
    **{'UTC{}'.format(i): f'Etc/GMT{-i}' if i >= 0 else f'Etc/GMT+{-i}' for i in range(-12, 13)}
}

def printc(text, fg=None, bg=None, bold=False, underline=False):
    codes = []
    if bold:
        codes.append(ANSI['bold'])
    if underline:
        codes.append(ANSI['underline'])
    if fg:
        codes.append(ANSI.get('fg_' + fg.lower(), ''))
    if bg:
        codes.append(ANSI.get('bg_' + bg.lower(), ''))
    style_prefix = ''.join(codes)
    return style_prefix + text + ANSI['reset']

def parse_to_utc(timestr, tzstr):
    naive = datetime.strptime(timestr, '%Y-%m-%d %H:%M:%S')
    tz = pytz.timezone(tzstr)
    localized = tz.localize(naive)
    return localized.astimezone(pytz.utc)

def calc_timeleft(target, tz, now):
    target = parse_to_utc(target, TZ_ALIAS_MAP[tz])
    if target < now:
        return '*-**:**:**'
    delta = target - now
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    remainder = total_seconds % 86400
    hours = remainder // 3600
    minutes = (remainder % 3600) // 60
    seconds = remainder % 60
    res = '{:d}-{:02d}:{:02d}:{:02d}'.format(days, hours, minutes, seconds)
    if delta <= timedelta(days=10):
        return printc(res, fg='red', bold=True)
    else:
        return res

def main(args):
    if os.path.exists('/opt/ddl/allacc.yml') and os.path.exists('/opt/ddl/all_conf.yaml') and os.path.exists('/opt/ddl/avai_conf.yaml'):
        if args.a:
            with open('/opt/ddl/all_conf.yaml', 'r', encoding='utf-8') as f:
                output_data = yaml.safe_load(f)
        else:
            with open('/opt/ddl/avai_conf.yaml', 'r', encoding='utf-8') as f:
                output_data = yaml.safe_load(f)
    else:
        print(printc('没有可用的ddl信息，请检查crontab中/opt/ddl/ddl_get_data是否正常运行', fg='red'))
        return

    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)

    if args.c:
        cato = args.c.upper()
        output_data = [data for data in output_data if data['sub'] == cato]
    if args.s:
        search_key = args.s.lower()
        output_data = [data for data in output_data if search_key in str(data).lower()]
    if args.rank:
        output_data = [data for data in output_data if data['rank'] == args.rank]
    if not (args.a or args.c or args.rank or args.s):
        keywords = ['icml','acl','naacl','nips','emnlp','iclr','aaai']
        pattern = re.compile('|'.join(map(re.escape, keywords)))
        output_data = [data for data in output_data if pattern.search(str(data))]

    if len(output_data) == 0:
        print(printc('No conference found.', fg='yellow'))
        return

    if not args.l:
        output_data.sort(key=lambda x: x['utc_deadline'])
        output_str = []
        for data in output_data:
            line = []
            line.append(data['title'] + str(data['year']))
            line.append(data['rank'])
            for tl in data['timeline']:
                line.append(tl['deadline'] + '(' + data['timezone'] + ')' if tl['deadline'] != 'TBD' else 'TBD')
                if tl['deadline'] != 'TBD':
                    line.append(calc_timeleft(tl['deadline'], data['timezone'], now_utc))
                else:
                    line.append('')
                output_str.append(line)
                line = ['', '']

        if args.p:
            print('|'.join(['CONFERENCE', 'CCF', 'DDL(TIMEZONE)', 'TIMELEFT']))
            for line in output_str:
                print('|'.join(line))
        else:
            align_length = [
                max([len(i[0]) for i in output_str] + [len('CONFERENCE')]),
                3,
                max([len(i[2]) for i in output_str] + [len('DDL(TIMEZONE)')]),
                11,
            ]
            formation = ("{{:<{}}} "*3 + "{{:<{}}}").format(*align_length)
            print(printc(formation.format('CONFERENCE', 'CCF', 'DDL(TIMEZONE)', 'TIMELEFT'), fg='cyan', bold=True))
            for line in output_str:
                print(formation.format(*line))
    else:
        output_data.sort(key=lambda x: x['utc_deadline'])
        with open('/opt/ddl/allacc.yml', 'r', encoding='utf-8') as f:
            allacc = yaml.safe_load(f)
        for data in output_data:
            print('[' + data['title'] + str(data['year']) + ']')
            print(data['description'])
            print("Sub: {}, CCF: {}, CORE: {}, THCPL: {}".format(data['sub'], data['ccf'], data['core'], data['thcpl']))
            print("Place: {}".format(data['place']))  # 不再 encode
            print("Date: {}".format(data['date']))
            print("Link: {}".format(data['link']))
            print("Timeline:")
            for i in data['timeline_raw']:
                if 'abstract_deadline' in i:
                    print("  Abstract deadline: {}".format(i['abstract_deadline']))
                print("  Deadline: {}".format(i['deadline']))
                if 'comment' in i:
                    print("  Comment: {}".format(i['comment']))
            print("Timezone: {}".format(data['timezone']))
            for i in allacc:
                if i['title'] == data['title']:
                    print("Accept_rates: {}".format(','.join(acc['str'] for acc in i['accept_rates'])))
                    break
            print()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='用于查看各种会议的ddl信息。数据来自于https://ccfddl.com/')
    parser.add_argument('-a', action='store_true', help='Show all conference ddl message')
    parser.add_argument('-c', type=str, help='Show conference ddl info of specific category')
    parser.add_argument('-s', type=str, help='Search info of specific conference')
    parser.add_argument('-l', action='store_true', help='Show detailed conference message')
    parser.add_argument('-p', action='store_true', help='Print conference ddl message in split of |')
    parser.add_argument('--rank', type=str, choices=['A', 'B', 'C'], help='Show message of ccfA/B/C conference')
    args = parser.parse_args()
    main(args)

#!/bin/python
# -*- coding: utf-8 -*-

import yaml
import codecs
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

    # 前景色（文字颜色）
    'fg_black':   '\033[30m',
    'fg_red':     '\033[31m',
    'fg_green':   '\033[32m',
    'fg_yellow':  '\033[33m',
    'fg_blue':    '\033[34m',
    'fg_magenta': '\033[35m',
    'fg_cyan':    '\033[36m',
    'fg_white':   '\033[37m',

    # 背景色
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
    'AoE': 'Etc/GMT+12',  # AoE = UTC-12
    'UTC': 'UTC',
    'UTC-12': 'Etc/GMT+12',
    'UTC-11': 'Etc/GMT+11',
    'UTC-10': 'Etc/GMT+10',
    'UTC-9':  'Etc/GMT+9',
    'UTC-8':  'Etc/GMT+8',
    'UTC-7':  'Etc/GMT+7',
    'UTC-6':  'Etc/GMT+6',
    'UTC-5':  'Etc/GMT+5',
    'UTC-4':  'Etc/GMT+4',
    'UTC-3':  'Etc/GMT+3',
    'UTC-2':  'Etc/GMT+2',
    'UTC-1':  'Etc/GMT+1',
    'UTC+0':  'Etc/GMT-0',  # 等价于 'UTC'
    'UTC+1':  'Etc/GMT-1',
    'UTC+2':  'Etc/GMT-2',
    'UTC+3':  'Etc/GMT-3',
    'UTC+4':  'Etc/GMT-4',
    'UTC+5':  'Etc/GMT-5',
    'UTC+6':  'Etc/GMT-6',
    'UTC+7':  'Etc/GMT-7',
    'UTC+8':  'Etc/GMT-8',
    'UTC+9':  'Etc/GMT-9',
    'UTC+10': 'Etc/GMT-10',
    'UTC+11': 'Etc/GMT-11',
    'UTC+12': 'Etc/GMT-12',
}


def printc(text, fg=None, bg=None, bold=False, underline=False):
    """
    彩色打印：支持前景色、背景色、加粗、下划线
    示例：
        printc("警告！", fg="yellow", bold=True)
        printc("错误！", fg="red", bg="white")
        printc("程序启动成功", fg="green")
        printc("注意：配置文件缺失", fg="yellow", bold=True)
        printc("错误：连接失败", fg="red", bg="white", bold=True)
        printc("下划线测试", fg="blue", underline=True)
    """
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
    # 解析成 datetime 对象并统一转成 UTC
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
            with codecs.open('/opt/ddl/all_conf.yaml', 'r', encoding='utf-8') as f:
                output_data = yaml.safe_load(f)
        else:
            with codecs.open('/opt/ddl/avai_conf.yaml', 'r', encoding='utf-8') as f:
                output_data = yaml.safe_load(f)
    else:
        print(printc('没有可用的ddl信息，请检查crontab中/opt/ddl/bin/ddl_get_data是否正常运行', fg='red'))
        return
    """
    每个data的格式：
    {
        title: ICML
        description: International Conference on Machine Learning
        sub: AI
        rank: A
        ccf: A
        core: A*
        thcpl: A
        dblp: icml
        year: 2025
        id: icml25
        link: https://icml.cc/Conferences/2025
        timeline: [
            {
            deadline: '2025-01-23 23:59:59'
            comment: Abstract Deadline
            }, 
            {
            deadline: '2025-01-30 23:59:59'
            comment: Paper Submissions Open on OpenReview Jan 08 2025 11:59 PM UTC
            }
        ]
        timeline_raw: [{raw data of timeline}]
        deadline: earliest avaiable ddl, e.g. 2025-01-23 23:59:59
        utc_deadline: deadline in UTC
        timezone: UTC-12
        date: July 11-19, 2025
        place: Vancouver Convention Center, Vancouver, Canada
    }
    注意不同的年份对应不同的data数据。这里不处理接受率的数据。
    """
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    # 筛选数据部分。默认只输出还没到截止时间的会议，除非指定-a参数。
    if args.c:
        # 筛选某个类别
        cato = args.c.upper()
        output_data = [data for data in output_data if data['sub']==cato]
    if args.s:
        # 搜索关键词
        search_key = args.s.lower()
        output_data = [data for data in output_data if search_key in str(data).lower()]
    if args.rank:
        # 筛选ccf排名
        output_data = [data for data in output_data if data['rank']==args.rank]
    if not (args.a or args.c or args.rank or args.s):
        # 如果不指定任何参数，默认输出六大会，即icml/acl/naacl/nips/emnlp/iclr/aaai
        keywords = ['icml','acl','naacl','nips','emnlp','iclr','aaai']
        pattern = re.compile('|'.join(map(re.escape, keywords)))
        output_data = [data for data in output_data if pattern.search(str(data))]
    
    if len(output_data) == 0:
        print(printc('No conference found.', fg='yellow'))
        return
    
    """
    格式输出部分。默认输出格式为
        CONFERENCE CCF DDL(TIMEZONE)            TIMELEFT
        ICML2025   A   2025-01-23 23:59:59(AoE) 4-12:34:56
                       2025-01-30 23:59:59(AoE) 11-12:34:56
    如果剩余时间在10天以内，则TIMELEFT部分用红色高亮表示
    TIMELEFT最小为0-00:00:00

    如果指定参数-p，则输出格式为
        '|'.join(data.keys())
        '|'.join(data1.values())
        '|'.join(data2.values())
        '|'.join(data3.values())
        ...
    
    如果指定参数-l，则输出格式为
        [ICML2025]
        International Conference on Machine Learning
        Sub: AI, CCF: A, CORE: A*, THCPL: A
        Place: Vancouver Convention Center, Vancouver, Canada
        Date: July 11-19, 2025
        Link: https://icml.cc/Conferences/2025
        Timeline:
            Abstract_deadline: 2025-01-23 23:59:59
            Deadline: 2025-01-30 23:59:59
            Comment: Paper Submissions Open on OpenReview Jan 08 2025 11:59 PM UTC
        Timezone: UTC-12
        Accept_rates: 27.9%(1827/6538 23'), 27.5%(2609/9473 24')
    此时参数-p无效
    """
    # for i in range(len(output_data)):
    #     if output_data[i]['deadline'] is None:
    #         output_data[i]['utc_deadline'] += timedelta(days=80000)
    if not args.l:
        output_data.sort(key=lambda x:x['utc_deadline'])
        output_str = []
        for data in output_data:
            line = []
            line.append(data['title']+str(data['year']))
            line.append(data['rank'])
            for tl in data['timeline']:
                line.append(tl['deadline']+'('+data['timezone']+')' if tl['deadline'] != 'TBD' else 'TBD')
                if tl['deadline'] != 'TBD':
                    line.append(calc_timeleft(tl['deadline'], data['timezone'], now_utc))
                else:
                    line.append('')
                output_str.append(line)
                line = ['','']

        if args.p:
            print('|'.join(['CONFERENCE', 'CCF', 'DDL(TIMEZONE)', 'TIMELEFT']))
            for line in output_str:
                print('|'.join(line))
        else:
            align_length = [
                max([len(i[0]) for i in output_str]+[len('CONFERENCE')]), 
                3, 
                max([len(i[2]) for i in output_str]+[len('DDL(TIMEZONE)')]),
                11,
            ]
            formation = ("{{:<{}}} "*3 + "{{:<{}}}").format(*align_length)
            print(formation.format('CONFERENCE', 'CCF', 'DDL(TIMEZONE)', 'TIMELEFT'))
            for i in range(len(output_str)):
                print(formation.format(*output_str[i]))
    else:
        output_data.sort(key=lambda x:x['utc_deadline'])
        with codecs.open('/opt/ddl/allacc.yml', 'r', encoding='utf-8') as f:
            allacc = yaml.safe_load(f)
        for data in output_data:
            print('['+data['title']+str(data['year'])+']')
            print(data['description'])
            print("Sub: {}, CCF: {}, CORE: {}, THCPL: {}".format(data['sub'], data['ccf'], data['core'], data['thcpl']))
            print("Place: {}".format(data['place'].encode('utf-8')))
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
            print('')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='用于查看各种会议的ddl信息。数据来自于https://ccfddl.com/')
    parser.add_argument('-a', action='store_true', help='Show all conference ddl message')
    parser.add_argument('-c', type=str, help='Show conference ddl info of specific category')
    parser.add_argument('-l', action='store_true', help='Show detailed conference message')
    # parser.add_argument('-o', type=str, help='Output format. Default is CONFERENCE RANK DDL(TIMEZONE) TIMELEFT')
    parser.add_argument('-p', action='store_true', help='Print conference ddl message in split of |')
    parser.add_argument('-s', type=str, help='Search info of specific conference')
    parser.add_argument('--rank', type=str, choices=['A', 'B', 'C'], help='Show message of ccfA/B/C conference')

    args = parser.parse_args()
    main(args)
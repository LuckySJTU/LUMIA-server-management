#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decode_migration.py  —  解析 Google Authenticator 的 otpauth-migration 数据并提取 TOTP secret

用法：
  python decode_migration.py "otpauth-migration://offline?data=Ci0B..."
  python decode_migration.py "Ci0B..."         # 只给 data 段也行
  python decode_migration.py -f qr_uri.txt     # 从文件读取

依赖：
  pip install protobuf
"""

import argparse
import base64
import re
import sys

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import DecodeError

# 映射常见数值到可读文本（仅用于输出，解析仍按整数处理）
ALGO_MAP = {
    0: "INVALID",
    1: "SHA1",
    2: "SHA256",
    3: "SHA512",
    4: "MD5",
}
OTP_TYPE_MAP = {
    0: "INVALID",
    1: "HOTP",
    2: "TOTP",
}
# Digits 在 migration.proto 里是枚举(0/6/8)，我们按数值原样显示
DIGITS_DEFAULT = 6

def build_migration_message_types():
    # 动态构建与 migration.proto 对应的两个消息，但把 enum 字段都按整数解析，避免 enum 声明导致的 type_name 问题
    fdp = descriptor_pb2.FileDescriptorProto()
    fdp.name = "migration.proto"
    fdp.syntax = "proto2"

    # message OTPParameters
    otp = fdp.message_type.add()
    otp.name = "OTPParameters"

    # bytes secret = 1;
    f = otp.field.add()
    f.name = "secret"
    f.number = 1
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_BYTES

    # optional string name = 2;
    f = otp.field.add()
    f.name = "name"
    f.number = 2
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

    # optional string issuer = 3;
    f = otp.field.add()
    f.name = "issuer"
    f.number = 3
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

    # optional int32 algorithm = 4;   // 原为 enum Algorithm
    f = otp.field.add()
    f.name = "algorithm"
    f.number = 4
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32

    # optional int32 digits = 5;      // 原为 enum DigitCount
    f = otp.field.add()
    f.name = "digits"
    f.number = 5
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32

    # optional uint64 counter = 6;    // HOTP 用
    f = otp.field.add()
    f.name = "counter"
    f.number = 6
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_UINT64

    # optional int32 type = 7;        // 原为 enum OtpType
    f = otp.field.add()
    f.name = "type"
    f.number = 7
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32

    # message MigrationPayload
    mp = fdp.message_type.add()
    mp.name = "MigrationPayload"

    # repeated OTPParameters otp_parameters = 1;
    f = mp.field.add()
    f.name = "otp_parameters"
    f.number = 1
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    f.type_name = ".OTPParameters"

    # 其余字段（version/batch_*）不是必须，这里可不声明

    pool = descriptor_pool.DescriptorPool()
    pool.Add(fdp)
    factory = message_factory.MessageFactory(pool)
    PayloadClass = factory.GetPrototype(pool.FindMessageTypeByName("MigrationPayload"))
    OTPClass = factory.GetPrototype(pool.FindMessageTypeByName("OTPParameters"))
    return PayloadClass, OTPClass

def _b64_urlsafe_decode_padded(s: str) -> bytes:
    s2 = s.strip().replace(" ", "").replace("\n", "")
    # URL-safe -> 标准
    s2 = s2.replace('-', '+').replace('_', '/')
    s2 += "=" * ((4 - (len(s2) % 4)) % 4)
    return base64.b64decode(s2)

def extract_data_from_input(text: str) -> str:
    # 优先从 URI 提取 data=xxxxx
    m = re.search(r"data=([A-Za-z0-9_\-]+)", text)
    if m:
        return m.group(1)
    # 否则尝试抓取一段较长的 URL-safe Base64
    cands = re.findall(r"[A-Za-z0-9_\-]{20,}", text)
    return max(cands, key=len) if cands else ""

def decode_migration(data_b64: str):
    PayloadClass, _ = build_migration_message_types()
    try:
        raw = _b64_urlsafe_decode_padded(data_b64)
    except Exception as e:
        raise ValueError(f"Base64 解码失败: {e}")

    payload = PayloadClass()
    try:
        payload.ParseFromString(raw)
    except DecodeError as e:
        raise ValueError(f"Protobuf 解析失败: {e}")

    results = []
    for otp in getattr(payload, "otp_parameters", []):
        secret_bytes = getattr(otp, "secret", b"")
        name = getattr(otp, "name", "")
        issuer = getattr(otp, "issuer", "")
        algorithm = getattr(otp, "algorithm", 0) or 0
        digits = getattr(otp, "digits", 0) or 0
        counter = getattr(otp, "counter", 0)
        otp_type = getattr(otp, "type", 0) or 0

        # Base32（常见做法去掉 '=' padding，很多客户端都接受）
        secret_b32 = base64.b32encode(secret_bytes).decode("utf-8").rstrip("=") if secret_bytes else ""

        # 人类可读
        algo_txt = ALGO_MAP.get(int(algorithm), str(algorithm))
        type_txt = OTP_TYPE_MAP.get(int(otp_type), str(otp_type))
        digits_val = int(digits) if int(digits) in (6, 8) else DIGITS_DEFAULT

        # 构造 otpauth URL（最常见参数）
        label = f"{issuer}:{name}" if issuer else name
        issuer_q = issuer
        otpauth_url = f"otpauth://totp/{label}?secret={secret_b32}"
        if issuer_q:
            otpauth_url += f"&issuer={issuer_q}"
        otpauth_url += f"&digits={digits_val}"

        results.append({
            "name": name,
            "issuer": issuer,
            "secret_base32": secret_b32,
            "digits": digits_val,
            "algorithm_code": int(algorithm),
            "algorithm": algo_txt,
            "counter": int(counter),
            "type_code": int(otp_type),
            "type": type_txt,
            "otpauth_url": otpauth_url,
        })
    return results

def main():
    ap = argparse.ArgumentParser(description="Decode Google Authenticator otpauth-migration data to TOTP secrets")
    ap.add_argument("input", nargs="?", help="完整的 otpauth-migration URI 或者 data 段（Base64）; 若不提供则读 stdin")
    ap.add_argument("-f", "--file", help="从文件读取 URI/data")
    args = ap.parse_args()

    if args.file:
        text = open(args.file, "r", encoding="utf-8").read()
    elif args.input:
        text = args.input
    else:
        text = sys.stdin.read().strip()

    data = extract_data_from_input(text)
    if not data:
        print("未找到 data。请提供形如 otpauth-migration://offline?data=xxxxx 或直接提供 xxxxx。", file=sys.stderr)
        sys.exit(2)

    try:
        res = decode_migration(data)
    except Exception as e:
        print("解码失败：", e, file=sys.stderr)
        sys.exit(3)

    if not res:
        print("解码成功，但没有找到任何 otp 参数。可能数据为空或不是 Google migration 格式。")
        sys.exit(0)

    print(f"共解析出 {len(res)} 个账号：\n")
    for i, r in enumerate(res, 1):
        print(f"#{i}")
        print("  issuer:    ", r["issuer"])
        print("  name:      ", r["name"])
        print("  secret:    ", r["secret_base32"])
        print("  digits:    ", r["digits"])
        print("  algorithm: ", f'{r["algorithm"]} ({r["algorithm_code"]})')
        print("  type:      ", f'{r["type"]} ({r["type_code"]})')
        print("  counter:   ", r["counter"])
        print("  otpauth:   ", r["otpauth_url"])
        print("")

if __name__ == "__main__":
    main()

# -*- coding: utf8 -*-

import main


def test_prefers_x_real_ip_when_present():
    headers = {'X-Real-IP': '203.0.113.5', 'X-Forwarded-For': '198.51.100.9'}
    assert main._resolve_real_ip(headers) == '203.0.113.5'


def test_falls_back_to_x_forwarded_for():
    headers = {'X-Forwarded-For': '198.51.100.9'}
    assert main._resolve_real_ip(headers) == '198.51.100.9'


def test_takes_first_hop_of_x_forwarded_for_chain():
    headers = {'X-Forwarded-For': '198.51.100.9, 10.0.0.1, 10.0.0.2'}
    assert main._resolve_real_ip(headers) == '198.51.100.9'


def test_unknown_when_neither_header_present():
    assert main._resolve_real_ip({}) == 'unknown'

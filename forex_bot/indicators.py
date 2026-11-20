def ema(values, period):
    if period <= 0 or len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out = []
    current = sum(values[:period]) / period
    out.append(current)
    for v in values[period:]:
        current = (v - current) * k + current
        out.append(current)
    return out


def atr(rates, period):
    if period <= 0 or len(rates) < period + 1:
        return []
    trs = []
    for i in range(1, len(rates)):
        h = rates[i].high
        l = rates[i].low
        c = rates[i - 1].close
        trs.append(max(h - l, abs(h - c), abs(l - c)))
    out = []
    current = sum(trs[:period]) / period
    out.append(current)
    for tr in trs[period:]:
        current = (current * (period - 1) + tr) / period
        out.append(current)
    return out

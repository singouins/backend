#!lua name=functions_pa

local VERSION = 3

-- A PA only counts once fully regenerated: pa = max - ceil(rem / dur)
-- Returns pa, ttnpa, rem (TTL >= 0), raw (Redis TTL: -2 absent, -1 no expiry)
local function read_pool(key, max, dur)
  local raw = redis.call('TTL', key)
  local rem = math.max(raw, 0)
  local missing = math.floor((rem + dur - 1) / dur)  -- ceil(rem/dur)
  local ttnpa = 0
  if rem > 0 then ttnpa = (rem - 1) % dur + 1 end    -- 1..dur, never 0 while regenerating
  return max - missing, ttnpa, rem, raw
end

-- A pool TTL down to 0 or below is a full pool: no key
local function write_pool(key, ttl)
  if ttl > 0 then
    redis.call('SET', key, 'None', 'EX', ttl)
  else
    redis.call('DEL', key)
  end
  return math.max(ttl, 0)
end

-- KEYS: blue, red
-- ARGV: red_cost, blue_cost, red_dur, blue_dur, red_max, blue_max
-- Returns {ok, red_spent, blue_spent, red_ttl, blue_ttl}: ok = 0 spends nothing
local function pa_consume(keys, args)
  local red_cost, blue_cost = tonumber(args[1]), tonumber(args[2])
  local red_dur, blue_dur = tonumber(args[3]), tonumber(args[4])
  local red_max, blue_max = tonumber(args[5]), tonumber(args[6])

  local blue, _, blue_ttl = read_pool(keys[1], blue_max, blue_dur)
  local red, _, red_ttl = read_pool(keys[2], red_max, red_dur)

  -- Q104: blue first, red covers the blue shortfall
  local blue_spent = math.min(blue_cost, math.max(blue, 0))
  local red_spent = red_cost + (blue_cost - blue_spent)
  if math.max(red, 0) < red_spent then
    return {0, 0, 0, red_ttl, blue_ttl}
  end

  if blue_spent > 0 then blue_ttl = write_pool(keys[1], blue_ttl + blue_spent * blue_dur) end
  if red_spent > 0 then red_ttl = write_pool(keys[2], red_ttl + red_spent * red_dur) end
  return {1, red_spent, blue_spent, red_ttl, blue_ttl}
end

-- KEYS: blue, red
-- ARGV: red, blue, red_dur, blue_dur
-- Gain or refund, capped at the pool max. Returns {red_ttl, blue_ttl}
local function give(key, n, dur)
  local ttl = redis.call('TTL', key)
  if ttl < 0 then return 0 end   -- already full
  if n <= 0 then return ttl end
  return write_pool(key, ttl - n * dur)
end

local function pa_add(keys, args)
  local red, blue = tonumber(args[1]), tonumber(args[2])
  local red_dur, blue_dur = tonumber(args[3]), tonumber(args[4])
  local blue_ttl = give(keys[1], blue, blue_dur)
  local red_ttl = give(keys[2], red, red_dur)
  return {red_ttl, blue_ttl}
end

-- KEYS: blue, red
-- ARGV: red_dur, blue_dur, red_max, blue_max
-- Returns {red_pa, red_ttnpa, red_ttl, blue_pa, blue_ttnpa, blue_ttl}
-- ttl is the raw Redis TTL (-2 absent, -1 no expiry), as in today's payload
local function pa_read(keys, args)
  local red_dur, blue_dur = tonumber(args[1]), tonumber(args[2])
  local red_max, blue_max = tonumber(args[3]), tonumber(args[4])
  local bp, bn, _, bt = read_pool(keys[1], blue_max, blue_dur)
  local rp, rn, _, rt = read_pool(keys[2], red_max, red_dur)
  return {rp, rn, rt, bp, bn, bt}
end

redis.register_function{function_name = 'pa_version', callback = function() return VERSION end, flags = {'no-writes'}}
redis.register_function('pa_consume', pa_consume)
redis.register_function('pa_add', pa_add)
redis.register_function{function_name = 'pa_read', callback = pa_read, flags = {'no-writes'}}
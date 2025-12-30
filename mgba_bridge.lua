lastkeys = nil
server = nil
ST_sockets = {}
nextID = 1

local BUTTON_MAP = {
    ["A"] = 0, ["B"] = 1, ["s"] = 2, ["S"] = 3,
    [">"] = 4, ["<"] = 5, ["^"] = 6, ["v"] = 7,
    ["R"] = 8, ["L"] = 9
}

local KEY_NAMES = { "A", "B", "s", "S", "<", ">", "^", "v", "R", "L" }

function ST_stop(id)
	local sock = ST_sockets[id]
	ST_sockets[id] = nil
	sock:close()
end

function ST_format(id, msg, isError)
	local prefix = "Socket " .. id
	if isError then
		prefix = prefix .. " Error: "
	else
		prefix = prefix .. " Received: "
	end
	return prefix .. msg
end

function ST_error(id, err)
	console:error(ST_format(id, err, true))
	ST_stop(id)
end

-- 1. Create a global "flag" at the top of your script (outside any function)
local releaseFrames = -1
local btnToRelease = nil

-- 2. Create the ONE and ONLY frame callback (outside the function)
callbacks:add("frame", function()
    if releaseFrames > 0 then
        releaseFrames = releaseFrames - 1
        if releaseFrames == 0 and btnToRelease ~= nil then
            emu:clearKey(btnToRelease)
            console:log("RELEASED: Key ID " .. btnToRelease)
            btnToRelease = nil
            releaseFrames = -1 -- Reset to idle state
        end
    end
end)

-- 3. Your fixed ST_received function
function ST_received(id)
    local sock = ST_sockets[id]
    if not sock then return end
    while true do
        local p, err = sock:receive(1024)
        if p then
            local cmd = p:match("^(.-)%s*$")
            local btn_id = BUTTON_MAP[cmd]

            if btn_id then
                -- If a button is already being held, clear it first
                if btnToRelease then emu:clearKey(btnToRelease) end

                -- Press the new button
                emu:addKey(btn_id)
                console:log("PRESSED: " .. cmd)

                -- Set the global timer for the frame callback to handle
                btnToRelease = btn_id
                releaseFrames = 6 -- Hold for 6 frames (0.1 seconds)
            end
        else
            if err ~= socket.ERRORS.AGAIN then
                ST_stop(id)
            end
            return
        end
    end
end

function ST_scankeys()
	local keys = emu:getKeys()
	if keys ~= lastkeys then
		lastkeys = keys
		local msg = "["
		for i, k in ipairs(KEY_NAMES) do
			if (keys & (1 << (i - 1))) == 0 then
				msg = msg .. " "
			else
				msg = msg .. k;
			end
		end
		msg = msg .. "]\n"
		for id, sock in pairs(ST_sockets) do
			if sock then sock:send(msg) end
		end
	end
end

function ST_accept()
	local sock, err = server:accept()
	if err then
		console:error(ST_format("Accept", err, true))
		return
	end
	local id = nextID
	nextID = id + 1
	ST_sockets[id] = sock
	sock:add("received", function() ST_received(id) end)
	sock:add("error", function() ST_error(id) end)
	console:log(ST_format(id, "Connected"))
end

callbacks:add("keysRead", ST_scankeys)

local port = 8888
server = nil
while not server do
	server, err = socket.bind(nil, port)
	if err then
		if err == socket.ERRORS.ADDRESS_IN_USE then
			port = port + 1
		else
			console:error(ST_format("Bind", err, true))
			break
		end
	else
		local ok
		ok, err = server:listen()
		if err then
			server:close()
			console:error(ST_format("Listen", err, true))
		else
			console:log("Socket Server Test: Listening on port " .. port)
			server:add("received", ST_accept)
		end
	end
end
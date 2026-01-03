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
    if sock then
        ST_sockets[id] = nil
        sock:close()
    end
end

function ST_format(id, msg, isError)
    local prefix = "Socket " .. tostring(id)
    if isError then
       prefix = prefix .. " Error: "
    else
       prefix = prefix .. " Received: "
    end
    -- Added tostring here to prevent "concatenate nil" errors
    return prefix .. tostring(msg)
end

function ST_error(id, err)
    console:error(ST_format(id, err, true))
    ST_stop(id)
end

local releaseFrames = -1
local btnToRelease = nil

callbacks:add("frame", function()
    if releaseFrames > 0 then
        releaseFrames = releaseFrames - 1
        if releaseFrames == 0 and btnToRelease ~= nil then
            emu:clearKey(btnToRelease)
            console:log("RELEASED: Key ID " .. btnToRelease)
            btnToRelease = nil
            releaseFrames = -1
        end
    end
end)

function ST_received(id)
    local sock = ST_sockets[id]
    if not sock then return end
    while true do
        local p, err = sock:receive(1024)

        -- FIX: Only process if 'p' is NOT nil
        if p ~= nil then
            local cmd = p:match("^(.-)%s*$")
            if cmd == "SAVE" then
                -- This tells mGBA to create a save state in Slot 1
                emu:saveState(1)
                console:log("SYSTEM: Hourly Save State Created in Slot 1")
                return -- Skip the normal button press logic for this command
            end

            -- Extra safety: Check if match found anything
            if cmd then
                local btn_id = BUTTON_MAP[cmd]

                if btn_id then
                    if btnToRelease then emu:clearKey(btnToRelease) end
                    emu:addKey(btn_id)
                    console:log("PRESSED: " .. cmd)
                    btnToRelease = btn_id
--                     releaseFrames = 6
                    if cmd == "^" or cmd == "v" or cmd == "<" or cmd == ">" then
                        releaseFrames = 14 -- Increased to 15 to ensure a full step
                    else
                        releaseFrames = 3  -- Keep menus/buttons snappy
                    end
                end
            end
        else
            -- If err is nil or not 'AGAIN', the socket closed/errored
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
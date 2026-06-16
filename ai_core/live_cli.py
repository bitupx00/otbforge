"""OTBForge Live CLI — Connect to RME Live Server and push maps in real-time.

Usage:
    python3 -m ai_core.cli live connect [host] [--port PORT] [--name NAME]
    python3 -m ai_core.cli live push [map_file.otbm] [host] [--port PORT] [--name NAME]
    python3 -m ai_core.cli live chat "message" [host] [--port PORT] [--name NAME]
    python3 -m ai_core.cli live generate "prompt" [host] [--port PORT] [--name NAME]

Examples:
    # Connect and monitor (interactive)
    python3 -m ai_core.cli live connect localhost --port 31313 --name OTBForge

    # Push an existing OTBM file to RME
    python3 -m ai_core.cli live push mymap.otbm localhost

    # Generate from prompt and push to RME
    python3 -m ai_core.cli live generate "tropical island with dungeon" localhost

    # Send chat message
    python3 -m ai_core.cli live chat "Map generation complete!" localhost
"""

import sys
import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cmd_connect(args):
    """Connect to RME Live Server and monitor events."""
    from ai_core.live_client import LiveClient

    host = args.host or "localhost"
    port = args.port or 31313
    name = args.name or "OTBForge"
    password = args.password or ""

    client = LiveClient(name=name, password=password)

    def on_chat(speaker, message):
        print(f"💬 [{speaker}] {message}")

    def on_operation_start(operation):
        print(f"⚡ Operation: {operation}")

    def on_operation_update(percent):
        bar_len = 40
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {percent}%", end="", flush=True)
        if percent >= 100:
            print()

    def on_connected(map_info):
        print(f"✅ Connected to map '{map_info.name}' ({map_info.width}x{map_info.height})")
        print("   Type messages to send as chat. Ctrl+C to disconnect.")

    def on_kicked(reason):
        print(f"❌ Kicked: {reason}")

    def on_disconnected(reason):
        print(f"⚠️  Disconnected: {reason}")

    client.on_chat = on_chat
    client.on_operation_start = on_operation_start
    client.on_operation_update = on_operation_update
    client.on_connected = on_connected
    client.on_kicked = on_kicked
    client.on_disconnected = on_disconnected

    try:
        print(f"🔗 Connecting to {host}:{port} as '{name}'...")
        if not client.connect(host, port):
            print("❌ Failed to connect")
            sys.exit(1)

        # Interactive mode — read lines and send as chat
        print()
        while client.connected:
            try:
                line = input()
                if line.strip():
                    client.send_chat(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nDisconnecting...")
                break

    except TimeoutError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ConnectionError as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)
    finally:
        client.close()


def cmd_push(args):
    """Push an OTBM file to RME Live Server."""
    from ai_core.live_client import LiveClient
    from ai_core.otbm_reader import OTBMReader

    map_file = args.map_file
    host = args.host or "localhost"
    port = args.port or 31313
    name = args.name or "OTBForge"

    # Read OTBM file
    print(f"📖 Reading {map_file}...")
    with open(map_file, "rb") as f:
        data = f.read()

    reader = OTBMReader(data=data)
    map_data = reader.read()
    tile_count = len(map_data.tiles)
    print(f"   Map: {map_data.width}x{map_data.height}, {tile_count} tiles")

    # Connect to server
    client = LiveClient(name=name)

    def on_chat(speaker, message):
        print(f"💬 [{speaker}] {message}")

    def on_connected(map_info):
        print(f"✅ Connected to map '{map_info.name}' ({map_info.width}x{map_info.height})")

    def on_kicked(reason):
        print(f"❌ Kicked: {reason}")

    client.on_chat = on_chat
    client.on_connected = on_connected
    client.on_kicked = on_kicked

    try:
        print(f"🔗 Connecting to {host}:{port}...")
        if not client.connect(host, port):
            print("❌ Failed to connect")
            sys.exit(1)

        # Push
        print(f"📤 Pushing {tile_count} tiles...")
        client.push_map(map_data, callback_progress=lambda stage, pct: print(f"  {stage} ({pct}%)"))
        print("✅ Done!")

    except TimeoutError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ConnectionError as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)
    finally:
        client.close()


def cmd_chat(args):
    """Send a single chat message to RME Live Server."""
    from ai_core.live_client import LiveClient

    message = args.message
    host = args.host or "localhost"
    port = args.port or 31313
    name = args.name or "OTBForge"

    client = LiveClient(name=name)

    try:
        print(f"🔗 Connecting to {host}:{port}...")
        if not client.connect(host, port, timeout=5):
            print("❌ Failed to connect")
            sys.exit(1)

        client.send_chat(message)
        print(f"✅ Sent: {message}")

    except TimeoutError as e:
        print(f"❌ {e}")
        sys.exit(1)
    finally:
        client.close()


def cmd_generate(args):
    """Generate a map from prompt and push to RME Live Server."""
    from ai_core.live_client import LiveClient
    from ai_core.map_validator import MapValidator

    prompt = args.prompt
    host = args.host or "localhost"
    port = args.port or 31313
    name = args.name or "OTBForge"

    # Generate map using compositor
    print(f"🧠 Generating map: '{prompt}'...")
    from ai_core.generators.compositor import CompositorConfig, FullMapGenerator

    # Parse prompt for basic settings
    cfg = CompositorConfig()
    if "small" in prompt.lower():
        cfg.width = 256
        cfg.height = 256
    elif "large" in prompt.lower():
        cfg.width = 1024
        cfg.height = 1024

    generator = FullMapGenerator(config=cfg)
    map_data = generator.generate()
    tile_count = len(map_data.tiles)
    print(f"   Generated: {map_data.width}x{map_data.height}, {tile_count} tiles")

    # Validate
    validator = MapValidator(map_data)
    issues = validator.validate()
    if issues:
        print(f"⚠️  {len(issues)} validation issues (non-critical)")
    else:
        print("✅ Validation passed")

    # Connect and push
    client = LiveClient(name=name)

    def on_chat(speaker, message):
        print(f"💬 [{speaker}] {message}")

    def on_connected(map_info):
        print(f"✅ Connected to map '{map_info.name}' ({map_info.width}x{map_info.height})")

    client.on_chat = on_chat
    client.on_connected = on_connected

    try:
        print(f"🔗 Connecting to {host}:{port}...")
        if not client.connect(host, port):
            print("❌ Failed to connect")
            sys.exit(1)

        print(f"📤 Pushing {tile_count} tiles to RME...")
        client.push_map(map_data, callback_progress=lambda stage, pct: print(f"  {stage} ({pct}%)"))
        print("✅ Map pushed to RME!")

    except TimeoutError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ConnectionError as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)
    finally:
        client.close()


def add_live_subparser(subparsers):
    """Add 'live' subcommand to CLI."""
    live_parser = subparsers.add_parser(
        "live",
        help="Connect to RME Live Server and push maps in real-time",
    )
    live_sub = live_parser.add_subparsers(dest="live_command", help="Live command")

    # connect
    conn = live_sub.add_parser("connect", help="Connect to RME Live Server (interactive)")
    conn.add_argument("host", nargs="?", default="localhost", help="Server host")
    conn.add_argument("--port", type=int, default=31313, help="Server port (default: 31313)")
    conn.add_argument("--name", default="OTBForge", help="Display name")
    conn.add_argument("--password", default="", help="Server password")

    # push
    push = live_sub.add_parser("push", help="Push OTBM file to RME Live Server")
    push.add_argument("map_file", help="OTBM file to push")
    push.add_argument("host", nargs="?", default="localhost", help="Server host")
    push.add_argument("--port", type=int, default=31313, help="Server port")
    push.add_argument("--name", default="OTBForge", help="Display name")

    # chat
    chat = live_sub.add_parser("chat", help="Send chat message")
    chat.add_argument("message", help="Message to send")
    chat.add_argument("host", nargs="?", default="localhost", help="Server host")
    chat.add_argument("--port", type=int, default=31313, help="Server port")
    chat.add_argument("--name", default="OTBForge", help="Display name")

    # generate
    gen = live_sub.add_parser("generate", help="Generate map from prompt and push")
    gen.add_argument("prompt", help="Map description prompt")
    gen.add_argument("host", nargs="?", default="localhost", help="Server host")
    gen.add_argument("--port", type=int, default=31313, help="Server port")
    gen.add_argument("--name", default="OTBForge", help="Display name")

    return live_parser


def handle_live_command(args):
    """Handle 'live' CLI subcommand."""
    cmd = getattr(args, "live_command", None)
    if cmd == "connect":
        cmd_connect(args)
    elif cmd == "push":
        cmd_push(args)
    elif cmd == "chat":
        cmd_chat(args)
    elif cmd == "generate":
        cmd_generate(args)
    else:
        print("Usage: python3 -m ai_core.cli live [connect|push|chat|generate] ...")
        sys.exit(1)

import cv2
import time

def view_channels():
    # --- CONFIGURATION ---
    IP_ADDRESS = "192.168.10.59"
    USERNAME = "Qwerty123"
    PASSWORD = "Qwerty888"
    PORT = "554"
    
    # Start at Channel 1
    current_channel = 1 
    
    # Store valid channels here (Format: {channel_number: url})
    known_channels = {}

    # --- URL TEMPLATES ---
    url_templates = [
        {
            "name": "XMeye / NetSurveillance (Standard)",
            "url": "rtsp://{ip}:{port}/user={u}&password={p}&channel={ch}&stream=0.sdp?"
        },
        {
            "name": "XMeye (Alternative)",
            "url": "rtsp://{ip}:{port}/user={u}_password={p}_channel={ch}_stream=0.sdp"
        },
        {
            "name": "Dahua / Amcrest",
            "url": "rtsp://{u}:{p}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=0"
        },
        {
            "name": "Hikvision / Generic NVR",
            "url": "rtsp://{u}:{p}@{ip}:{port}/Streaming/Channels/{ch}01" 
        },
        {
            "name": "Generic Simple",
            "url": "rtsp://{u}:{p}@{ip}:{port}/{ch}" 
        }
    ]

    print(f"--- PHASE 1: Detecting URL Pattern for {IP_ADDRESS} ---")
    
    working_template = None
    
    # Step 1: Find the correct pattern using Channel 1
    for template in url_templates:
        test_url = template["url"].format(u=USERNAME, p=PASSWORD, ip=IP_ADDRESS, port=PORT, ch=1)
        print(f"Testing: {template['name']}...")
        
        cap = cv2.VideoCapture(test_url)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"\nSUCCESS! Locked onto pattern: {template['name']}")
                working_template = template["url"]
                cap.release()
                break
        cap.release()

    if not working_template:
        print("\nError: Could not connect to Channel 1 using common patterns.")
        return

    # Step 2: The Loop (Surfing Channels)
    print("\n" + "="*60)
    print(f"--- PHASE 2: CHANNEL SURFING ---")
    print("CONTROLS:")
    print("  [ n ]  -> Next Camera")
    print("  [ p ]  -> Previous Camera")
    print("  [ q ]  -> Quit")
    print("="*60 + "\n")

    while True:
        rtsp_url = working_template.format(u=USERNAME, p=PASSWORD, ip=IP_ADDRESS, port=PORT, ch=current_channel)
        
        print(f"Loading Channel {current_channel}...")
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            print(f"Channel {current_channel} not available (or camera offline).")
            print("Press 'n' to try next, 'p' for previous, 'q' to quit.")
            
            # Wait for key press even if video failed
            while True:
                key = cv2.waitKey(100) & 0xFF
                if key == ord('n'):
                    current_channel += 1
                    break
                elif key == ord('p'):
                    if current_channel > 1: current_channel -= 1
                    break
                elif key == ord('q'):
                    return
            continue

        # --- SUCCESS: Add to Known List and Print ---
        known_channels[current_channel] = rtsp_url
        
        print("\n" + "-"*20 + " DISCOVERED CHANNELS " + "-"*20)
        # Sort by channel number so it looks nice (1, 2, 3...)
        for ch_num in sorted(known_channels.keys()):
            prefix = ">> " if ch_num == current_channel else "   "
            print(f"{prefix}Channel {ch_num}: {known_channels[ch_num]}")
        print("-" * 61 + "\n")
        # --------------------------------------------

        # Show Video Loop
        window_name = f"Camera Channel {current_channel} (Press n/p/q)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Lost stream.")
                break
            
            cv2.imshow(window_name, frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('n'):
                current_channel += 1
                break 
            elif key == ord('p'):
                if current_channel > 1:
                    current_channel -= 1
                break 
            elif key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                return

        cap.release()
        cv2.destroyWindow(window_name)

if __name__ == "__main__":
    view_channels()

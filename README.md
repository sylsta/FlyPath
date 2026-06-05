<div align="center">
  <img src="icon.png" width="96" alt="FlyPath icon"/>
</div>

# FlyPath

**FlyPath** is an open-source QGIS plugin for planning autonomous drone mapping missions and exporting them as native DJI WPML KMZ files — no conversion tools or third-party apps required.

Define your survey area directly on the map, configure flight parameters, preview the path, and export a ready-to-fly mission file loadable in the DJI Fly app.

Developed and maintained by [Dronnix](https://www.dronnix.com) — a drone mapping and geospatial AI company.

---

## Screenshots

![FlyPath panel overview](docs/images/panel_overview.png)

![Flight path preview on map](docs/images/map_preview.png)

---

## Key Features

- Draw the survey area directly on the QGIS map canvas using a native polygon drawing tool
- Import a survey area from any polygon layer or active QGIS selection
- Configurable flight altitude, speed, gimbal angle, photo interval, side overlap, and flight direction
- Time-based interval photo triggering (`multipleTiming`) — matches DJI Mini 4 Pro and Mini 3 Pro native auto interval capture
- Calculated front overlap display — shows effective along-track overlap from speed × interval with low-overlap warnings
- Auto-optimised flight direction based on survey area geometry
- Live GSD and effective photo spacing — synced to drone model, altitude, speed, and interval
- Flight statistics: area, path distance, waypoint count, photo count, estimated batteries, and flight time
- Configurable safety actions: finish action and RC lost action
- Exports native DJI WPML KMZ — compatible with DJI Fly on DJI RC2
- **Direct RC export**: set the RC waypoint folder path once — FlyPath automatically finds and replaces the latest mission on the controller via USB
- **Local folder export**: set any local or external drive path — FlyPath saves directly to that folder
- Contextual info bar — hover over any parameter to see what it does
- Dark-themed dock panel — designed to complement the QGIS interface

---

## Requirements

| Requirement | Details |
|---|---|
| Operating System | ✅ Windows 10 / 11 |
| QGIS | 3.16 or later |
| Python | 3.9+ (bundled with QGIS) |
| Drone | DJI Mini 3 Pro or DJI Mini 4 Pro |
| Controller | DJI RC2 (for direct USB export) |

> 🐧 Linux and macOS support is planned for a future release.

---

## Installation

### Option A — Install from ZIP *(recommended for now)*

1. Download the latest `FlyPath.zip` from the [Releases](https://github.com/dronnix-io/FlyPath/releases) page
2. In QGIS go to **Plugins → Manage and Install Plugins → Install from ZIP**
3. Select the downloaded ZIP and click **Install Plugin**

### Option B — Build from source

```shell
git clone https://github.com/dronnix-io/FlyPath.git
```

Copy the `FlyPath` folder into your QGIS plugins directory:

```
Windows: C:\Users\<you>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\
```

Then enable it in QGIS via **Plugins → Manage and Install Plugins → Installed → FlyPath**.

### Launch the plugin

After installation, open FlyPath via:

**Plugins → FlyPath → FlyPath**

Or click the **FlyPath icon** in the QGIS toolbar. The plugin opens as a dock panel on the right side of the QGIS window.

---

## Workflow

### Step 1 — Define the survey area

Three ways to define your survey polygon:

- **Draw on Map** — click the button to activate the drawing tool, left-click to place vertices, right-click to finish. Backspace removes the last vertex, Escape cancels.
- **Layer / Feature** — select any polygon layer and feature already loaded in QGIS.
- **Use QGIS Selection** — select a polygon feature on the map canvas using QGIS's native selection tools, then click **Use QGIS Selection**.

Only one polygon can be active at a time. Switching methods automatically removes the previous survey area.

### Step 2 — Configure flight parameters

#### Flight Parameters

| Parameter | Description |
|---|---|
| Drone Model | Sets camera specs used for GSD and spacing calculations |
| Altitude | Flight altitude above ground level (AGL) in metres |
| GSD | Calculated ground sampling distance — updates live with altitude |
| Side Overlap | Cross-track strip spacing overlap — controls distance between flight lines |
| Speed | Waypoint flight speed in m/s (max 12 m/s) |
| Direction | Angle of flight lines — or click **Auto** to optimise for the survey shape |
| Margin | Buffer added around the survey polygon boundary in metres |

#### Camera Settings

| Parameter | Description |
|---|---|
| Gimbal Angle | Camera tilt: −90° points straight down (nadir) for 2D mapping |
| Photo Interval | Time between photos in seconds (minimum 2 s at 12 MP JPEG) |
| Shot Spacing | Calculated: speed × interval in metres — updates live |
| Front Overlap | Calculated: effective along-track overlap percentage — turns red if too low |

> **Note:** Front overlap is a derived value, not a manual input. Adjust speed or interval to control it.

#### Safety Actions

| Parameter | Description |
|---|---|
| Finish Action | What the drone does after the last waypoint (Return to Home / Hover / Land) |
| RC Lost Action | What the drone does if RC signal is lost (Return to Home / Hover / Land / Continue) |

GSD, shot spacing, and front overlap update live as you adjust parameters.

### Step 3 — Preview on Map

Click **Preview on Map** to generate the flight grid and display it on the canvas:

- **Deep pink polygon** — survey area boundary
- **Electric yellow lines** — flight path connecting all waypoints
- **Electric yellow circles** — mid-waypoints
- **Red filled circle** — start waypoint
- **Blue filled circle** — end waypoint

Flight statistics (area, distance, photos, batteries, flight time) update below the parameters.

![Export bar](docs/images/export_bar.png)

### Step 4 — Export KMZ

FlyPath supports three export workflows depending on the RC path field:

---

#### Workflow A — Direct RC Export (automatic)

This workflow replaces a mission directly on the DJI RC2 via USB — no manual copying or renaming required.

**Prerequisites:**
- Create at least one dummy waypoint mission in DJI Fly on the RC (even a 3-point mission works). This creates the UUID folder that FlyPath will replace.
- Connect the RC2 to your PC via USB.

**Setup (one time only):**

1. Click **Browse…** next to the RC path field — File Explorer opens at *This PC*
2. Navigate to: `DJI RC 2 › Internal shared storage › Android › data › dji.go.v5 › files › waypoint`
3. Click the address bar to reveal the full path, copy it (Ctrl+C)
4. Paste it into the RC path field in FlyPath — the path saves automatically

**Exporting:**

1. Click **Export KMZ**
2. FlyPath finds the most recent mission UUID on the RC, writes the new KMZ, and copies it directly into the UUID folder
3. A success message confirms which mission was replaced
4. Disconnect the RC, close and reopen DJI Fly — the updated mission will appear in the waypoints list

---

#### Workflow B — Local Folder Export

Use this workflow to save the KMZ to a specific folder on your PC or an external drive.

1. Paste any local folder path (e.g. `F:\missions`) into the RC path field and click **Set**
2. Click **Export KMZ** — FlyPath saves `FlyPath_Mission.kmz` directly to that folder
3. If the folder does not exist, FlyPath will offer to create it

---

#### Workflow C — Manual Export

Use this workflow when no path is configured, or when you prefer to manage files manually.

1. Leave the RC path field empty
2. Click **Export KMZ** — a standard save dialog opens
3. Choose a destination and filename on your PC
4. Connect your DJI RC2 via USB
5. In File Explorer, navigate to the RC's waypoint folder:
   `This PC › DJI RC 2 › Internal shared storage › Android › data › dji.go.v5 › files › waypoint`
6. Open the UUID folder of an existing mission (created by DJI Fly)
7. Copy the exported KMZ into that folder and rename it to `<UUID>.kmz` — matching the folder name exactly
8. Disconnect the RC, close and reopen DJI Fly — the mission will appear updated

---

## Supported Drones

| Drone | Waypoint Support | droneEnumValue | Verification |
|---|---|---|---|
| DJI Mini 3 Pro | Yes | 97 | Community-verified |
| DJI Mini 4 Pro | Yes | 68 | Verified from native RC2 mission dump |

> **Note:** DJI Mini 3 (standard) does **not** support waypoint missions and is not supported by FlyPath.

---

## Project Structure

```
FlyPath/
├── flypath.py            # QGIS plugin entry point
├── flypath_dialog.py     # Main UI panel and export logic
├── map_tools.py          # Interactive polygon drawing tool
├── grid_planner.py       # Flight grid and waypoint generation
├── wpml_writer.py        # DJI WPML KMZ file writer
├── metadata.txt          # QGIS plugin metadata
├── icon.png              # Plugin icon
├── icon.svg              # Plugin icon source
└── docs/
    └── images/           # README screenshots
```

---

## Known Limitations

- ⚠️ Tested and verified on Windows 10 / 11 only — Linux and macOS support is planned for a future release
- Direct RC export requires a DJI RC2 connected via USB with at least one existing mission
- DJI Mini 3 Pro droneEnumValue (`97`) is community-verified — not confirmed from a native mission file
- 2D grid missions only — no terrain following, 3D facade, or orbit missions
- No automatic multi-battery mission splitting

---

## Changelog

### v1.0.3
- Changed survey area colour to deep pink (#FF1493) for higher map contrast
- Changed flight path colour to electric yellow (#FFE600)
- Start waypoint changed to red, start and end markers enlarged
- Drawing tool rubber band and vertex markers now match the deep pink survey colour
- Right-click now places the final vertex before finishing the polygon
- Removed Set button — RC path saves automatically as you type

### v1.0.2
- Switched photo triggering to time-based interval (`multipleTiming`) — matches DJI Mini 4 Pro / Mini 3 Pro native auto interval capture
- Added Photo Interval parameter (2.0–60.0 s)
- Added Gimbal Angle control (−90° to −30°)
- Front overlap is now a calculated read-only field with colour warnings
- Added RC Lost Action to Safety Actions
- Fixed speed not applying on DJI RC (was defaulting to 2.5 m/s)
- Fixed export to local folders and external drives
- Fixed duplicate dock widget warning on plugin reload
- Max speed capped at 12 m/s
- Removed manual Front Overlap, Altitude Mode, and Mission Name parameters

### v1.0.1
- Fixed TypeError on map preview for QGIS 3.38+
- Fixed label placement enum error on QGIS 3.38+

### v1.0.0
- Initial stable release

---

## Contributing

Contributions are welcome. To get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes
4. Open a pull request against `main`

For bug reports and feature requests, please use the [issue tracker](https://github.com/dronnix-io/FlyPath/issues).

---

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

---

## About Dronnix

[Dronnix](https://www.dronnix.com) is a drone mapping and geospatial AI company specialising in data collection and analysis for solar panel inspection, agriculture, urban growth monitoring, construction progress tracking, and large-scale mapping missions.

FlyPath is part of Dronnix's open tooling layer — free and open-source to support the drone mapping community.

**Contact:** [salar@dronnix.com](mailto:salar@dronnix.com)

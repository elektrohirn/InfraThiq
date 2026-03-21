BMS – Gebäudeautomationssystem / Building Management System
Entwickelt im Rahmen einer Umschulung als Portfolioprojekt zur Bewerbung bei Beckhoff Automation.
Developed as a portfolio project during vocational retraining, submitted as part of an application to Beckhoff Automation.

Deutsch
Projektbeschreibung
Dieses Projekt ist ein vollständig funktionsfähiges Gebäudemanagementsystem (BMS) auf Basis von Python und Flask. Es simuliert und steuert die Gebäudetechnik eines mehrzimmerigen Bürogebäudes – inklusive Regellogik, adaptivem Lernen, Präsenzerfassung und einer modernen Tablet-Oberfläche.

Das System wurde von Grund auf selbst entwickelt und zeigt, wie industrielle Automatisierungssoftware strukturiert und umgesetzt werden kann – mit klarer Trennung zwischen Hardware-Schnittstelle, Regellogik und Benutzeroberfläche.

Funktionsumfang
Raumregelung – Temperatur, CO₂, Licht und Jalousien werden automatisch geregelt
Vier Aktuatoren pro Raum – Lüftung (CO₂-gesteuert), Heizung, Kühlung, Jalousie (strahlungsabhängig)
Adaptive Lernlogik – Das System erkennt Anwesenheitsmuster einzelner Mitarbeiter und passt die Regelung automatisch an
Präsenzerfassung – NFC-basiertes Ein- und Auschecken pro Raum
Zeiterfassung – Anwesenheitsprotokoll mit Tagesbericht
Tablet-Interface – Moderne 5-seitige Wischnavigation für den Einsatz am Touchscreen
Browser-Interface – Vollständiges Wartungs- und Konfigurationsinterface
Dynamische Raumverwaltung – Räume können zur Laufzeit hinzugefügt und entfernt werden
Logging – Vollständiges Systemprotokoll mit CSV-Export
TwinCAT 3 / Beckhoff ADS – Vorbereitet für echte SPS-Anbindung (siehe unten)
Architektur & Module
Datei	Aufgabe
main.py	Hauptschleife – koordiniert alle Module, Terminal-Dashboard
simulation.py	Physikalische Simulation (Temperatur, CO₂, Licht, Sonnenverlauf)
control.py	Regellogik für alle vier Aktuatoren
adaptive.py	Maschinelles Lernen – Anwesenheitsmuster, Wahrscheinlichkeiten
presence.py	Präsenzerfassung und Raumzuordnung
attendance.py	Zeiterfassung mit Check-in / Check-out
actuator.py	Aktuator-Klasse mit Auto- und Manualmodus
roomstore.py	Persistente Raumkonfiguration (rooms.json)
sps.py	SPS-Schnittstelle – Simulation oder echte TwinCAT-Verbindung
tablet_data.py	Profilverwaltung, Szenen, Radio, Kantine, Meetings
webserver.py	Flask-Server – REST-API, Browser-Interface, Tablet-Interface
logger.py	Systemprotokoll
Installation & Start
Voraussetzungen:

Python 3.10 oder höher
pip
Abhängigkeiten installieren:

pip install flask
System starten:

cd src
python main.py
Interfaces öffnen:

Browser-Interface (Wartung): http://localhost:5000
Tablet-Interface: http://localhost:5000/tablet
TwinCAT 3 / Beckhoff ADS Anbindung
Das System ist von Grund auf für die Anbindung an eine echte Beckhoff-SPS vorbereitet. Die gesamte Hardware-Kommunikation ist in sps.py isoliert – alle anderen Module bleiben unverändert.

Hybridmodus: Wenn TwinCAT verbunden ist, werden echte Sensorwerte eingelesen und überschreiben die simulierten Werte. Bei Verbindungsverlust läuft die Simulation automatisch weiter – ohne Unterbrechung.

Für echten Betrieb benötigt:

pip install pyads
Dann in sps.py die AMS Net ID und den Port der SPS eintragen:

AMS_NET_ID = "192.168.1.5.1.1"
ADS_PORT   = 851
Variablenkonvention in der SPS (TwinCAT GVL):

GVL.Buero_co2        → REAL
GVL.Buero_temp       → REAL
GVL.Buero_occupancy  → REAL
GVL.Buero_vent       → REAL  (Schreiben)
GVL.Buero_heat       → REAL  (Schreiben)
GVL.Buero_cool       → REAL  (Schreiben)
GVL.Buero_blind      → REAL  (Schreiben)
Die Anbindung an echte Beckhoff-Hardware war bewusst für das Pflichtpraktikum vorgesehen.

English
Project Description
This project is a fully functional Building Management System (BMS) built with Python and Flask. It simulates and controls the building technology of a multi-room office building – including control logic, adaptive learning, presence tracking, and a modern tablet interface.

The system was developed entirely from scratch and demonstrates how industrial automation software can be structured and implemented – with a clear separation between hardware interface, control logic, and user interface.

Features
Room control – Temperature, CO₂, lighting and blinds are regulated automatically
Four actuators per room – Ventilation (CO₂-driven), heating, cooling, blinds (radiation-dependent)
Adaptive learning – The system recognises attendance patterns of individual employees and adjusts control accordingly
Presence tracking – NFC-based check-in and check-out per room
Attendance logging – Attendance records with daily reports
Tablet interface – Modern 5-page swipe navigation designed for touchscreen use
Browser interface – Full maintenance and configuration interface
Dynamic room management – Rooms can be added and removed at runtime
Logging – Complete system log with CSV export
TwinCAT 3 / Beckhoff ADS – Prepared for real PLC integration (see below)
Architecture & Modules
File	Purpose
main.py	Main loop – coordinates all modules, terminal dashboard
simulation.py	Physical simulation (temperature, CO₂, light, sun position)
control.py	Control logic for all four actuators
adaptive.py	Machine learning – attendance patterns, probabilities
presence.py	Presence tracking and room assignment
attendance.py	Time tracking with check-in / check-out
actuator.py	Actuator class with automatic and manual mode
roomstore.py	Persistent room configuration (rooms.json)
sps.py	PLC interface – simulation or real TwinCAT connection
tablet_data.py	Profile management, scenes, radio, canteen, meetings
webserver.py	Flask server – REST API, browser interface, tablet interface
logger.py	System log
Installation & Start
Requirements:

Python 3.10 or higher
pip
Install dependencies:

pip install flask
Start the system:

cd src
python main.py
Open interfaces:

Browser interface (maintenance): http://localhost:5000
Tablet interface: http://localhost:5000/tablet
TwinCAT 3 / Beckhoff ADS Integration
The system is built from the ground up to support connection to a real Beckhoff PLC. All hardware communication is isolated in sps.py – all other modules remain unchanged.

Hybrid mode: When TwinCAT is connected, real sensor values are read and override the simulated values. If the connection is lost, the simulation continues automatically – without interruption.

For real operation:

pip install pyads
Then set the AMS Net ID and port of the PLC in sps.py:

AMS_NET_ID = "192.168.1.5.1.1"
ADS_PORT   = 851
Variable convention in the PLC (TwinCAT GVL):

GVL.Buero_co2        → REAL
GVL.Buero_temp       → REAL
GVL.Buero_occupancy  → REAL
GVL.Buero_vent       → REAL  (write)
GVL.Buero_heat       → REAL  (write)
GVL.Buero_cool       → REAL  (write)
GVL.Buero_blind      → REAL  (write)
The integration with real Beckhoff hardware was intentionally planned for the mandatory internship.

Entwickelt mit Python 3 · Flask · pyads · Beckhoff TwinCAT 3
Developed with Python 3 · Flask · pyads · Beckhoff TwinCAT 3

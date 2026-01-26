*****************************************************
               Real Estate Calculator
*****************************************************

---------------------
1. Description
---------------------
This project is a Real Estate Calculator written in Python.
It provides a full calculation of real estate transactions in Israel,
including purchase tax, capital gains tax, broker fees, lawyer fees,
recognized expenses, and net difference between selling and buying.

The application includes:
- A full GUI built with Tkinter
- Automatic tax bracket extraction from gov.il (with fallback)
- Purchase tax breakdown per bracket
- Graphical visualization using Matplotlib
- History of up to 10 saved calculations
- Support for EXE packaging via PyInstaller

---------------------
2. Features
---------------------
- Capital gains tax calculation (מס שבח)
- Purchase tax calculation (מס רכישה)
- Automatic parsing of tax brackets from gov.il
- Stacked bar chart showing purchase tax brackets
- Save and view calculation history
- Clear history option
- Hebrew GUI with English code documentation
- EXE support with resource_path handling

---------------------
3. Technologies Used
---------------------
- Python 3.11+
- Tkinter
- Matplotlib
- Requests
- BeautifulSoup4
- PyInstaller

---------------------
4. How It Works
---------------------
1. The user enters sale and purchase details:
   - Sale price
   - Broker and lawyer percentages
   - Original purchase price
   - Recognized expenses
   - Exemption limit
   - New purchase price and fees

2. The calculator computes:
   - Capital gains tax
   - Purchase tax
   - Total sale net
   - Total purchase cost
   - Net difference (profit or required addition)

3. A stacked bar chart is generated showing purchase tax brackets.

4. The user may:
   - Save the calculation
   - View history
   - Clear history

---------------------
5. Usage
---------------------
1. Run the file "RealEstateCalc.py" or the packaged EXE.
2. Fill in the fields in the GUI.
3. Click "חשב" to perform the calculation.
4. View results on the left and tax breakdown on the right.
5. Use "שמור חישוב" to save the current calculation.
6. Use "הצג היסטוריית חישובים" to view saved results.
7. Use "מחק היסטוריה" to clear all saved calculations.

---------------------
6. Build EXE
---------------------
To build a standalone executable:

pip install pyinstaller
pyinstaller --onefile --noconsole --add-data "SellHouse.png;." --add-data "BuyHouse.png;." RealEstateCalc.py

The EXE will be created in the "dist" folder.

---------------------
7. Project Files
---------------------
- RealEstateCalc.py     : Main application code
- SellHouse.png         : Optional image for sale section
- BuyHouse.png          : Optional image for purchase section
- README.md             : Project documentation

---------------------
8. Notes
---------------------
- If gov.il is unavailable, the calculator uses fallback tax brackets.
- GUI labels are in Hebrew; code comments and logic are in English.
- This project is intended for educational and personal use.
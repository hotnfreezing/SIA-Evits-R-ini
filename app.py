import streamlit as st
from ckanapi import RemoteCKAN
from fpdf import FPDF
import datetime
import os
from num2words import num2words

# --- 1. GRAMATIKA (Simt septiņdesmit divi eiro...) ---
from num2words import num2words # Pārliecinies, ka šī rinda ir koda pašā augšā

def format_summa_vardos(n):
    # SVARĪGI: Noapaļojam pašu summu uzreiz, lai izvairītos no 99.999... kļūdas
    n = round(n, 2)
    euro = int(n)
    centi = int(round((n - euro) * 100))
    
    # Drošības spilvens - ja pēc matemātiskām darbībām centi tomēr sanāk 100
    if centi == 100:
        euro += 1
        centi = 0
    
    try:
        p = num2words(euro, lang='lv')
    except:
        return f"{n:.2f} eiro"

    # Saglabājam visus iepriekšējos gramatikas labojumus
    if p.startswith("tūkstotis"): p = "viens " + p
    if p.startswith("simts"): p = "viens " + p
    simti_list = ["divi", "trīs", "četri", "pieci", "seši", "septiņi", "astoņi", "deviņi"]
    for s in simti_list:
        p = p.replace(f"{s} simts", f"{s} simti")

    p = p.capitalize()
    
    # Centu gramatika
    cents_text = "centi"
    if centi % 10 == 1 and centi % 100 != 11:
        cents_text = "cents"
    elif centi % 10 == 0 or (11 <= centi % 100 <= 19):
        cents_text = "centu"
    
    res = f"{p} eiro un {centi:02d} {cents_text}"
    return res

# --- 2. MEKLĒŠANA UR DATUBĀZĒ ---
def search_company_sql(query):
    if len(query) < 3: return []
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) billing_app/1.0'
    rc = RemoteCKAN('https://data.gov.lv/dati/', user_agent=ua)
    rid = "25e80bf3-f107-4ab4-89ef-251b5b9374e9"
    
    # Notīrām vaicājumu no liekām pēdiņām, kas var saplēst SQL
    clean_q = query.replace('"', '').replace("'", "").strip()
    
    try:
        # 1. Mēģinājums: Vienkāršā meklēšana (visdrošākā pret kļūdām)
        result = rc.action.datastore_search(resource_id=rid, q=clean_q, limit=15)
        records = result.get('records', [])
        
        # Ja atrada, atgriežam tūlīt
        if records:
            return records
            
        # 2. Mēģinājums (ja 1. nekas nav): SQL vaicājums nosaukumam un reģ. nr.
        sql = f"SELECT * FROM \"{rid}\" WHERE name ILIKE '%%{clean_q}%%' OR regcode ILIKE '%%{clean_q}%%' LIMIT 15"
        result_sql = rc.action.datastore_search_sql(sql=sql)
        return result_sql.get('records', [])
        
    except Exception as e:
        # Ja kaut kas noiet greizi, mēģinām vismaz atgriezt tukšu sarakstu, nevis kļūdu
        st.error(f"Meklēšanas kļūda: {e}")
        return []

# --- 3. NUMURĀCIJA ---
def get_next_invoice_id():
    file_path = "invoice_counter.txt"
    year_short = datetime.date.today().strftime("%y")
    prefix = f"EVI{year_short}"
    current_num = 5
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                current_num = int(f.read().strip()) + 1
        except: pass
    return f"{prefix}{current_num:03d}", current_num

# --- 4. PDF ĢENERĒŠANA ---
def create_pdf(client, items, inv_num, supplier, due_date, vatin_client, vat_rate):
    pdf = FPDF()
    pdf.add_page()
    
    f_name = "Helvetica"
    if os.path.exists("arial.ttf"):
        try:
            pdf.add_font("ArialLV", style="", fname="arial.ttf")
            f_name = "ArialLV"
            if os.path.exists("arialbd.ttf"):
                pdf.add_font("ArialLV", style="B", fname="arialbd.ttf")
            if os.path.exists("ariali.ttf"):
                pdf.add_font("ArialLV", style="I", fname="ariali.ttf")
            else:
                pdf.add_font("ArialLV", style="I", fname="arial.ttf")
        except:
            f_name = "Helvetica"

    def t(txt):
        if f_name == "Helvetica":
            repl = {'ā':'a','č':'c','ē':'e','ģ':'g','ī':'i','ķ':'k','ļ':'l','ņ':'n','š':'s','ū':'u','ž':'z',
                    'Ā':'A','Č':'C','Ē':'E','Ģ':'G','Ī':'I','Ķ':'K','Ļ':'L','Ņ':'N','Š':'S','Ū':'U','Ž':'Z'}
            for k, v in repl.items(): txt = str(txt).replace(k, v)
        return str(txt)

    # Galvene
    pdf.set_font(f_name, "B", 14)
    pdf.cell(0, 10, t(f"Preču pavadzīme - rēķins Nr. {inv_num}"), ln=True, align='R')
    pdf.set_font(f_name, "", 10)
    pdf.cell(0, 5, t(f"Datums: {datetime.date.today().strftime('%d.%m.%Y.')}"), ln=True, align='R')
    pdf.cell(0, 5, t(f"Apmaksas termiņš: {due_date.strftime('%d.%m.%Y.')}"), ln=True, align='R')
    
    pdf.ln(10)
    y_parties = pdf.get_y()
    
    # Piegādātājs (Bold nosaukums, Reģ. Nr. dalīts)
    pdf.set_font(f_name, "B", 10); pdf.text(10, y_parties, t("Piegādātājs:"))
    pdf.set_xy(10, y_parties + 2); pdf.cell(90, 32, "", border=1)
    
    pdf.set_xy(12, y_parties + 4)
    pdf.set_font(f_name, "B", 10); pdf.cell(86, 5, t(supplier['name']), ln=1)
    
    pdf.set_font(f_name, "", 9); pdf.set_x(12)
    pdf.cell(40, 5, t("Reģ. Nr."), 0, 0, 'L')
    pdf.cell(46, 5, t(supplier['reg']), 0, 1, 'R')
    
    pdf.set_x(12)
    p_info = f"PVN: {supplier['vatin']}\nAdrese: {supplier['addr']}\nIBAN: {supplier['iban']}"
    pdf.multi_cell(86, 5, t(p_info), border=0)

    # Saņēmējs (Bold nosaukums, Reģ. Nr. dalīts)
    pdf.set_font(f_name, "B", 10)
    pdf.text(110, y_parties, t("Saņēmējs:"))
    
    pdf.set_xy(110, y_parties + 2)
    pdf.cell(90, 32, "", border=1) # Rāmītis paliek
    
    pdf.set_xy(112, y_parties + 4)
    pdf.set_font(f_name, "B", 10)
    # IZMAIŅA: multi_cell ļauj nosaukumam aizņemt vairākas rindas
    pdf.multi_cell(86, 4.5, t(client['name']), border=0)
    
    # Lai Reģ. Nr. neuzkāptu virsū nosaukumam, mēs dinamiski turpinām no esošās pozīcijas
    pdf.set_x(112)
    pdf.set_font(f_name, "", 9)
    pdf.cell(40, 5, t("Reģ. Nr."), 0, 0, 'L')
    pdf.cell(46, 5, t(client['reg']), 0, 1, 'R')
    
    pdf.set_x(112)
    pvn_val = vatin_client if vatin_client else ""
    c_info = f"PVN: {pvn_val}\nAdrese: {client['addr']}"
    pdf.multi_cell(86, 5, t(c_info), border=0)
    

    # Tabula un pārējais (bez izmaiņām)
    pdf.set_y(y_parties + 40)
    pdf.set_fill_color(240, 240, 240); pdf.set_font(f_name, "B", 9)
    pdf.cell(10, 8, "Nr.", 1, 0, 'C', True)
    pdf.cell(85, 8, t("Nosaukums"), 1, 0, 'L', True)
    pdf.cell(15, 8, t("Mērv."), 1, 0, 'C', True)
    pdf.cell(20, 8, t("Daudzums"), 1, 0, 'C', True)
    pdf.cell(25, 8, t("Cena"), 1, 0, 'C', True)
    pdf.cell(35, 8, t("Summa"), 1, 1, 'C', True)
    
    total_net = 0
    pdf.set_font(f_name, "", 9)
    for i, item in enumerate(items, 1):
        line_sum = item['qty'] * item['price']
        total_net += line_sum
        pdf.cell(10, 8, str(i), 1, 0, 'C')
        pdf.cell(85, 8, t(item['name']), 1)
        pdf.cell(15, 8, t(item['unit']), 1, 0, 'C')
        pdf.cell(20, 8, f"{item['qty']:.2f}", 1, 0, 'C')
        pdf.cell(25, 8, f"{item['price']:.2f}", 1, 0, 'R')
        pdf.cell(35, 8, f"{line_sum:.2f}", 1, 1, 'R')

    pdf.ln(5)
    rate_val = vat_rate if isinstance(vat_rate, (int, float)) else 0
    vat_sum = total_net * (rate_val / 100)
    grand = total_net + vat_sum
    
    pdf.set_x(130)
    pdf.cell(35, 8, t("Summa bez PVN:"), 0, 0, 'R')
    pdf.cell(35, 8, f"{total_net:.2f} EUR", 1, 1, 'R')
    
    if vat_rate != "Bez PVN":
        pdf.set_x(130)
        pdf.cell(35, 8, t(f"PVN {vat_rate}%:"), 0, 0, 'R')
        pdf.cell(35, 8, f"{vat_sum:.2f} EUR", 1, 1, 'R')

    pdf.set_x(130); pdf.set_font(f_name, "B", 10)
    pdf.cell(35, 10, t("KOPĀ:"), 0, 0, 'R')
    pdf.cell(35, 10, f"{grand:.2f} EUR", 1, 1, 'R', fill=True)
    
    # Summa vārdiem (Italic)
    pdf.ln(5); pdf.set_font(f_name, "", 9)
    pdf.write(8, t("Summa vārdiem: "))
    pdf.set_font(f_name, "I", 9); pdf.write(8, t(format_summa_vardos(grand)))
    
    if pdf.get_y() < 250: pdf.set_y(-30)
    else: pdf.ln(15)
        
    pdf.set_font(f_name, "", 8)
    pdf.cell(0, 10, t("Dokuments sagatavots elektroniski un ir derīgs bez paraksta."), align="C", ln=True)
    
    return pdf.output()

# --- 5. STREAMLIT UI ---
st.set_page_config(page_title="SIA Evits", layout="wide")

if 'inv_rows' not in st.session_state:
    st.session_state.inv_rows = [{'name': 'Ēdināšanas pakalpojumi', 'unit': 'gab.', 'qty': 1.0, 'price': 0.0}]

st.title("📄 SIA Evits rēķinu sistēma")
my_data = {"name": "SIA Evits", "reg": "45403040896", "vatin": "LV45403040896", "addr": "Zvanītāju iela 27, Jēkabpils, LV-5201", "iban": "LV42UNLA0050022886954"}

c1, c2 = st.columns(2)
with c1:
    st.subheader("🔍 Pircēja meklēšana")
    search_q = st.text_input("Ieraksti nosaukumu")
    f_name, f_reg, f_addr, f_vat = "", "", "", ""
    
    if len(search_q) >= 3:
        hits = search_company_sql(search_q)
        if hits:
            opts = {f"{str(h.get('name', 'Nezināms'))} ({str(h.get('regcode') or h.get('reg_code') or '?')})": h for h in hits}
            choice = st.selectbox("Izvēlies uzņēmumu:", ["-- Izvēlies --"] + list(opts.keys()))
            if choice != "-- Izvēlies --":
                d = opts[choice]
                f_name = str(d.get('name') or "")
                raw_reg = str(d.get('regcode') or d.get('reg_code') or "").strip()
                f_reg = raw_reg
                f_vat = f"LV{raw_reg}" if raw_reg else ""
                
                addr_base = str(d.get('address') or d.get('legal_address') or "").strip()
                raw_idx = str(d.get('post_code') or d.get('zip_code') or d.get('index') or "").strip()
                
                if raw_idx and raw_idx != "None":
                    idx = raw_idx if raw_idx.startswith("LV-") else f"LV-{raw_idx}"
                    f_addr = f"{addr_base}, {idx}" if idx not in addr_base else addr_base
                else: f_addr = addr_base

    st.divider()
    is_pvn_client = st.checkbox("Klients ir PVN maksātājs", value=True)
    in_name = st.text_input("Pircēja nosaukums", value=f_name)
    in_reg = st.text_input("Reģistrācijas numurs", value=f_reg)
    in_vat = st.text_input("PVN numurs", value=f_vat if is_pvn_client else "")
    in_addr = st.text_input("Juridiskā adrese", value=f_addr)

with c2:
    st.subheader("🛒 Preces un Rēķina dati")
    
    inv_no_auto, raw_no = get_next_invoice_id()
    final_inv_no = st.text_input("Rēķina numurs", value=inv_no_auto)
    
    termins_dienas = st.number_input("Apmaksas termiņš (dienas)", min_value=0, max_value=90, value=7, step=1)
    due_date_calc = datetime.date.today() + datetime.timedelta(days=termins_dienas)
    
    vat_choice = st.selectbox("PVN likme", [21, 12, 0, "Bez PVN"], index=0)
    
    st.write("---")
    new_items = []
    for i, item in enumerate(st.session_state.inv_rows):
        cols = st.columns([3, 1, 1, 1, 0.5])
        u_val = item.get('unit', 'gab.')
        n = cols[0].text_input("Prece", value=item['name'], key=f"n_{i}")
        u = cols[1].text_input("Mērv.", value=u_val, key=f"u_{i}")
        q = cols[2].number_input("Daudzums", value=float(item['qty']), key=f"q_{i}")
        p = cols[3].number_input("Cena", value=float(item['price']), key=f"p_{i}", format="%.2f")
        
        new_items.append({'name': n, 'unit': u, 'qty': q, 'price': p})
        if cols[4].button("🗑️", key=f"d_{i}"):
            st.session_state.inv_rows.pop(i); st.rerun()
            
    st.session_state.inv_rows = new_items
    if st.button("➕ Pievienot jaunu rindu"):
        st.session_state.inv_rows.append({'name': 'Ēdināšanas pakalpojumi', 'unit': 'gab.', 'qty': 1.0, 'price': 0.0})
        st.rerun()

st.divider()

if st.button("🚀 Ģenerēt un Lejupielādēt PDF"):
    if not in_name: 
        st.error("Lūdzu, aizpildi klienta datus!")
    else:
        pdf_out = create_pdf(
            {"name": in_name, "reg": in_reg, "addr": in_addr}, 
            st.session_state.inv_rows, 
            final_inv_no, 
            my_data, 
            due_date_calc,
            in_vat, 
            vat_choice
        )
        
        with open("invoice_counter.txt", "w") as f: 
            f.write(str(raw_no))
            

        st.download_button("📥 Lejupielādēt PDF", data=bytes(pdf_out), file_name=f"Rekins_{final_inv_no}.pdf")













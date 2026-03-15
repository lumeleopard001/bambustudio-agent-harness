# Alustamine — BambuStudio + Claude Desktop

See juhend on sulle, kes:
- Omad Bambu Lab printerit (A1, A1 mini, P1S, X1C vms)
- Kasutad BambuStudio'd igapäevaselt
- Kasutad Claude Desktop'i macOS-is
- **Ei ole programmeerija** — sa ei pea koodi kirjutama

Lõpptulemus: sa saad Claude'ile öelda "Slici see fail minu A1 printerile" ja Claude teeb seda sinu eest.

---

## Mida sa vajad

Enne alustamist kontrolli, et sul on:

1. **BambuStudio** — installeeritud ja töötab ([lae alla siit](https://bambulab.com/en/download/studio))
2. **Claude Desktop** — installeeritud macOS-is ([lae alla siit](https://claude.ai/download))
3. **Python** — macOS-il on tavaliselt olemas. Kui pole, installeeri: ava Terminal ja kirjuta `brew install python@3.12`

Ei tea kas Python on olemas? Ava Terminal (Cmd+Space → kirjuta "Terminal" → Enter) ja kirjuta:
```
python3 --version
```
Kui näed "Python 3.10" või uuem — kõik korras.

---

## Paigaldamine (5 minutit)

### Samm 1: Ava Terminal

Vajuta **Cmd + Space** (Spotlight), kirjuta **Terminal**, vajuta **Enter**.

### Samm 2: Kopeeri ja kleebi need 3 rida

Kopeeri kõik 3 rida korraga (Cmd+C) ja kleebi Terminali (Cmd+V), siis vajuta Enter:

```bash
git clone https://github.com/lumeleopard001/bambustudio-agent-harness.git
cd bambustudio-agent-harness
bash install.sh
```

Installer teeb kõik automaatselt:
- Kontrollib Python'i ja BambuStudio olemasolu
- Installib tööriista
- Seadistab Claude Desktop'i MCP ühenduse (kui Claude Desktop on installeeritud)

Kui näed `[OK] Installation complete!` — kõik on valmis!

### Samm 3: Taaskäivita Claude Desktop

Sulge Claude Desktop täielikult (paremklikk Dock'is → Quit) ja ava uuesti.
Claude näeb nüüd BambuStudio tööriista.

---

## Kuidas kasutada

### Lihtsaim viis: küsi Claude'ilt

Ava Claude Desktop ja kirjuta loomulikus keeles. Näiteks:

> **Sina:** Mul on Downloads kaustas fail phone_stand.stl. Slici see minu A1 printerile PLA-ga.

> **Claude:** Slicin faili sinu Bambu Lab A1 printerile PLA materjaliga standard kvaliteediga...
>
> Tulemus:
> - Prindiaeg: 45 minutit
> - Filament: 12.3g PLA
> - Projekt salvestatud: /tmp/bambustudio_auto_.../phone_stand_project.3mf
>
> Avan slicitud projekti BambuStudios...
> BambuStudio avaneb automaatselt. Vaata mudel üle ja vajuta "Send to Printer".

### Veel näiteid, mida Claude'ilt küsida

**Materjalivalik:**
> "Ma tahan printida vaasi. Millist materjali soovitad?"

Claude selgitab: "Vaas on dekoratiivne objekt, soovitan PLA-d — see on lihtne, ei vaja kuumendust ega kinnist kammerit. Kui vaas puutub veega kokku, soovitan PETG-d."

**Kvaliteedivalik:**
> "Prindin telefonikesta. Kas fine või standard?"

Claude selgitab: "Telefonikesta puhul soovitan fine (0.12mm kihid) — pind on siledam ja detail parem. Standard (0.20mm) on kiirem, aga kihijooned on nähtavad."

**Filamendi jälgimine:**
> "Kui palju mul valget PLA-d alles on?"

> "Lisa uus rull: Bambu PLA Basic, sinine, AMS pessa 3"

> "Vaheta AMS pesa 2 punase PETG vastu"

**Olemasoleva projekti ülevaade:**
> "Vaata üle mu Desktop/project.3mf — kas seaded on mõistlikud?"

Claude analüüsib projekti ja annab soovitusi: "Layer height on 0.28mm (draft) — see sobib prototüübile, aga viimistletud eseme jaoks soovitan 0.12-0.20mm."

---

## Kust mudeleid saada?

3D mudelite allalaadimine on tasuta:

| Leht | Aadress | Sobib... |
|------|---------|----------|
| **MakerWorld** | [makerworld.com](https://makerworld.com) | Bambu Lab'i ametlik, parimad Bambu-optimeeritud mudelid |
| **Printables** | [printables.com](https://printables.com) | Suur valik, hea kvaliteet |
| **Thingiverse** | [thingiverse.com](https://thingiverse.com) | Suurim kogukond, kõige rohkem valikut |

1. Otsi mudel (nt "phone stand", "vase", "shelf bracket")
2. Lae alla STL fail
3. Fail läheb tavaliselt Downloads kausta
4. Ütle Claude'ile: "Slici Downloads/phone_stand.stl minu A1 printerile"

---

## Kuidas tulemust BambuStudios avada

Kui Claude on mudeli sliceinud, avab ta tulemuse **automaatselt BambuStudios**. Sa näed kohe slicitud mudelit — kihid, tugimaterjalid, prindiaeg. Vajuta "Send to Printer" kui kõik sobib.

### Variant A: Automaatne (vaikimisi)

Claude avab BambuStudio ise pärast slicimist. Sind ei pea midagi tegema.

Kui see mingil põhjusel ei käivitu, ütle lihtsalt:
> "Ava see fail BambuStudios"

### Variant B: Käsitsi avamine

Kui eelistad ise avada:
1. Ava **BambuStudio**
2. Mine **File → Open Project**
3. Vajuta **Cmd + Shift + G** (Go to Folder)
4. Kleebi failitee, mille Claude andis
5. Vali `.3mf` fail ja vajuta Open

---

## Filamendi jälgimine

Kui sul on AMS (Automatic Material System), saad Claude'ile öelda millised rullid on laetud:

```
Lisa rull 1: Bambu PLA Basic, valge, AMS pesa 1
Lisa rull 2: Bambu PLA Basic, must, AMS pesa 2
```

Pärast iga printi arvab Claude automaatselt maha, kui palju filamendilt kulus.
Kui rull hakkab otsa saama, hoiatab Claude sind.

Küsi igal ajal: **"Kui palju filamenti alles on?"**

---

## Uuendamine

Kui tööriist on juba paigaldatud ja tahad uusima versiooni saada:

```
cd bambustudio-agent-harness
git pull
bash install.sh
```

Taaskäivita Claude Desktop pärast uuendamist.

---

## Tõrkeotsing

**"BambuStudio not found"**
→ Installeeri BambuStudio: [bambulab.com/en/download/studio](https://bambulab.com/en/download/studio)

**Claude ei näe BambuStudio tööriista**
→ Taaskäivita Claude Desktop (sulge ja ava uuesti)
→ Kui ei aita, kontrolli terminalis: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json`

**"Python not found"**
→ Ava Terminal ja kirjuta: `brew install python@3.12`
→ Kui `brew` pole olemas: kopeeri [brew.sh](https://brew.sh) lehelt installiskript

**Installer ütleb viga**
→ Proovi uuesti: `cd bambustudio-agent-harness && bash install.sh`

---

## Mida Claude teeb ja mida mitte

| Claude teeb | Claude ei tee |
|------------|---------------|
| Slicib STL faile ja avab tulemuse BambuStudios | Ei saada printi otse printerisse |
| Soovitab materjali, kvaliteeti, täidist | Ei tee mudelite disaini (kasutad selleks Tinkercad vms) |
| Jälgib filamendi kasutust | Ei loe AMS-ist otse (slotid tuleb käsitsi registreerida) |
| Analüüsib olemasolevaid projekte | Ei muuda projekte visuaalselt (selleks kasuta BambuStudio GUI-d) |
| Selgitab miks üht või teist seadet kasutada | Ei otsusta sinu eest — sina valid, Claude soovitab |

---

*Küsimuste korral: kirjuta Claude'ile! Ta aitab sind samm-sammult edasi.*

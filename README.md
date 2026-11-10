# pdf_assistant

> **Status (2026-11-10): zamrznut kao demo.** Aplikacija radi i demo ostaje uživo, ali se ovde ne dodaju
> nove funkcije. Sve što bi ovde bilo sledeće (skenovi i OCR, folderi, više dokumenata, zajednička baza
> znanja) već postoji u [document-buddy](https://github.com/ManSe404/document-buddy), koji prelazi na
> biblioteku Mosaic. Ispravke grešaka su i dalje dobrodošle.

Razgovor sa jednim PDF-om. Korisnik otpremi PDF i postavlja pitanja, a odgovori
navode stranu iz koje dolaze. PDF stoji pored razgovora i klik na izvor otvara tu
stranu.

Aplikacija je i mali eksperiment. Svaki razgovor nasumično dobija jedan jezički model,
broj isečaka koji se pretražuju i količinu istorije koja ide modelu. Korisnici ocenjuju
odgovore palcem gore ili dole, a novi razgovori češće dobijaju kombinacije sa boljim
ocenama. Strana „Ocene” pokazuje kako koja komponenta prolazi.

## Demo

**[Otvori interaktivni demo →](https://manse404.github.io/pdf_assistant/demo/)**

Demo radi u browseru, bez servera i ključeva, nad izmišljenim dokumentima i sa unapred
napisanim odgovorima. Izgleda kao prava aplikacija, a lokalno se otvara direktno kao
`docs/demo/index.html`. U njemu može da se:

- **postavlja pitanja o ugovoru** ili kućnom redu. Odgovor se strimuje, a klik na `[1]`
  skroluje PDF na tu stranu i označi je.
- **postavi nastavak razgovora** („A depozit?”), koji se pre pretrage prepisuje u
  samostalno pitanje, i pitanje van dokumenta („Ko je direktor zakupca?”).
- **oceni odgovor** palcem, pa na strani „Ocene” vidi kako se menjaju zadovoljstvo i
  šansa da komponenta bude izabrana.
- **otpremi primer PDF-a.** Jedan prođe obradu do „Spreman”, a jedan, skeniran, završi
  kao „Greška” sa objašnjenjem.
- **otvori panel „Ispod haube”.** Za svaki korak pokazuje šta bi backend uradio:
  - izvlačenje modela, broja isečaka i istorije, sa verovatnoćama;
  - prepisivanje nastavka razgovora;
  - pronađene isečke sa stranama i ocenom sličnosti;
  - budžet prompta, NDJSON strim i Langfuse trag.
- **probati podešavanja** u kartici „Podešavanja” istog panela: Claude, Foundry,
  OpenAI, Ollama ili mešano; Qdrant ili Pinecone; eksperiment i tracing. Tu je i
  simulacija pada modela usred odgovora. Kartica ispisuje odgovarajući `.env`.

[![Razgovor sa izvorima i panel „Ispod haube”](docs/demo/razgovor.png)](https://manse404.github.io/pdf_assistant/demo/?view=doc&state=done&hood=1)

[![Ocene komponenti eksperimenta](docs/demo/ocene.png)](https://manse404.github.io/pdf_assistant/demo/?view=scores&state=done)

## Šta sve ima

| Oblast | Šta postoji |
|---|---|
| Nalozi | Registracija i prijava (bcrypt, sesija u httpOnly kolačiću), odjava; registracija se gasi sa `ALLOW_SIGNUP=false`. Svaki korisnik vidi samo svoje PDF-ove i razgovore. |
| PDF-ovi | Otpremanje do 50 MB (`MAX_UPLOAD_MB`) sa trakom napretka, provera da je fajl PDF, obrada u pozadini sa statusom (obrađuje se / spreman / greška), nastavak obrade posle restarta, brisanje (fajl, vektori, razgovori). |
| Pregled | PDF pored razgovora (pdf.js, strane se crtaju tek kad dođu u vidno polje), tekst može da se označi, brojač strana; na telefonu kartice Razgovor / PDF. |
| Razgovor | Više razgovora po PDF-u (izbor, novi, brisanje), naslov po prvom pitanju, strimovan odgovor, Markdown, izvori `[n]` koji vode na stranu, lista odlomaka, prepisivanje nastavka razgovora (`REWRITE_FOLLOWUPS`), „dokument to ne navodi” kad odgovora nema. |
| Eksperiment | Model, broj isečaka i istorija biraju se po razgovoru, ponderisano ocenama; palac gore/dole po odgovoru (može da se promeni ili povuče); strana „Ocene” sa zadovoljstvom i težinom izbora; `EXPERIMENTS=false` ga gasi. |
| Modeli | Claude (API ili Microsoft Foundry), OpenAI, Azure OpenAI / Foundry, Ollama; svaki model u `CHAT_MODELS` može da ima svog provajdera. Embedding: OpenAI, Azure, Ollama. |
| Pretraga | Qdrant (ugrađen ili server) ili Pinecone; isečci od 1000 znakova sa preklopom, svaki pamti stranu; budžet prompta (`MAX_PROMPT_TOKENS`). |
| Praćenje | Langfuse tragovi za pitanje i obradu PDF-a (korisnik = user, razgovor = session), kad postoje ključevi. |
| Skladište | Baza: SQLite ili Postgres. PDF-ovi: disk ili privatni Supabase Storage bucket. Supabase radi i lokalno (`npx supabase start`) i u cloudu; tabele su zatvorene za Supabase-ov javni Data API. |
| Rad | Jedan proces (API + obrada + izgrađen klijent), SQLite i fajlovi u `data/` podrazumevano, Alembic migracije, Docker slika, OpenAPI na `/api/docs`. |

## Kako radi

```
otpremanje → PDF na disk ili u Supabase Storage → tekst po stranama (pypdfium2) → isečci sa brojem strane
          → embedding → baza vektora (Qdrant ili Pinecone, imenski prostor po PDF-u)

pitanje → (nastavak razgovora se prepisuje u samostalno pitanje)
        → embedding pitanja → k najbližih isečaka ovog PDF-a
        → prompt sa numerisanim isečcima [1], [2] i stranama → model strimuje odgovor
        → odgovor se čuva sa izvorima koje navodi
```

- **Indeksiranje** ide u pozadini, u istom procesu kao API. PDF je „obrađuje se” dok
  ne postane „spreman” ili „greška”, a greška se prikazuje uz PDF. Ako se proces
  ugasi usred obrade, PDF se ponovo obrađuje pri sledećem startu.
- **Skenirani PDF** (bez tekstualnog sloja) završava kao greška sa objašnjenjem: OCR
  ovde ne postoji. Za skenove je napravljen document-buddy.
- **Odgovor** se strimuje kao NDJSON događaji (`start`, `delta`, `end` ili `error`).
  Odgovor koji se prekine ne čuva se, a pitanje bez odgovora se izostavlja iz
  istorije.
- **Prompt** ima budžet (`MAX_PROMPT_TOKENS`). Prvo idu isečci, pa celi parovi
  pitanje–odgovor iz istorije, od najnovijeg.

### Eksperiment

Kada razgovor počne, za svaku vrstu komponente izvlači se jedna, ponderisano ocenama:

| Vrsta | Podešava se sa | Podrazumevano |
|---|---|---|
| jezički model | `CHAT_MODELS` | `claude-opus-5-5`, `claude-sonnet-5-5` |
| broj isečaka | `RETRIEVER_TOP_K` | 3, 5, 8 |
| istorija | `MEMORY_TURNS` (0 = cela istorija) | cela, poslednja 2 pitanja |

- **Težina komponente** je `(gore + 1) / (gore + dole + 1)`, najmanje 0,1. Ono „+1” je
  jedan zamišljeni palac gore, pa komponenta bez ocena važi za odličnu i dobija
  priliku. Donja granica sprečava da loše ocenjena komponenta potpuno nestane.
- **Ocene se ne gube:** ostaju i kada se razgovor ili PDF obriše.
- `EXPERIMENTS=false` gasi eksperiment, pa svaki razgovor dobija prvu komponentu sa
  svake liste.

## Pokretanje

Potrebni su [uv](https://docs.astral.sh/uv/) i Node 24 (ili 22.17+; u `client/` je `.nvmrc`, pa `nvm use`). Node 25 ne može da instalira zavisnosti klijenta, jer ga vitest 5 ne podržava. Podrazumevano se
ne podiže nijedan servis, jer su SQLite i Qdrant fajlovi u `backend/data/`. Ključevi
modela idu u `backend/.env`:

```bash
ANTHROPIC_API_KEY=...     # odgovori (Claude)
OPENAI_API_KEY=...        # embedding
```

```bash
backend/bin/init.sh                          # baza (može više puta)
backend/bin/api.sh                           # API na http://127.0.0.1:8000, docs na /api/docs
cd client && npm install && npm run dev      # klijent na http://127.0.0.1:5173
```

Vite prosleđuje `/api` na `http://127.0.0.1:8000`; drugi port se zadaje sa
`API_URL=http://127.0.0.1:8010 npm run dev`. Prvi nalog se pravi na strani za
registraciju. Ako ključ fali, API se zaustavi pri startu i u logu napiše koju
promenljivu treba postaviti.

**Docker:** `docker compose up --build` pravi jednu sliku (izgrađen klijent +
API) na <http://localhost:8000>. Podaci su u volumenu `data`, a promenljive se čitaju
iz `.env` pored `docker-compose.yml`.

**Bez ključeva, preko Ollame:**

```bash
CHAT_PROVIDER=ollama
CHAT_MODELS=llama3.2,gemma4:31b-cloud
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBED_DOCUMENT_PREFIX="search_document: "
EMBED_QUERY_PREFIX="search_query: "
```

Iz Dockera Ollama mora da sluša na svim adresama (`OLLAMA_HOST=0.0.0.0`), jer kontejner
gađa `host.docker.internal:11434`.

Za bazu i PDF-ove u Supabase-u (lokalno ili cloud) vidi [Supabase](#supabase-lokalno-i-cloud).

## Podešavanja

Sve ide preko promenljivih okruženja ili `backend/.env`. Kompletan spisak je u
`backend/src/pdf_assistant/settings.py`.

| Promenljiva | Podrazumevano | Napomena |
|---|---|---|
| `ENVIRONMENT` | `dev` | Van `dev` mora da postoji `SECRET_KEY`, a kolačić je `Secure`. |
| `SECRET_KEY` | dev vrednost | Potpisuje kolačić sesije. |
| `ALLOW_SIGNUP` | `true` | `false` zatvara registraciju. |
| `DATA_DIR` | `backend/data` | SQLite, PDF-ovi, ugrađeni Qdrant. |
| `DATABASE_URL` | SQLite u `DATA_DIR` | SQLAlchemy URL. `postgresql://…` (npr. iz Supabase-a) radi takav kakav je, drajver je psycopg 3. |
| `MAX_UPLOAD_MB` | `50` | |
| `PDF_STORAGE` | `disk` | `disk` (`DATA_DIR/pdfs`) ili `supabase`. |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_BUCKET` | , , `pdfs` | Za `PDF_STORAGE=supabase`, vidi niže. Ključ je secret (`sb_secret_…`) ili stari `service_role`; ide samo u backend. |
| `CHAT_PROVIDER`, `CHAT_MODELS` | `anthropic`, `claude-opus-5-5,claude-sonnet-5-5` | Stavka može da ima i svog provajdera: `openai:gpt-5.1`. |
| `CLAUDE_EFFORT` | `low` | Samo Claude: `low` … `max`, ili `default`. |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` | `openai`, `text-embedding-3-small` | Promena traži novu kolekciju ili indeks. Claude nema embedding. |
| `RETRIEVER_TOP_K`, `MEMORY_TURNS`, `EXPERIMENTS` | `3,5,8`, `0,2`, `true` | Eksperiment, vidi gore. |
| `REWRITE_FOLLOWUPS` | `true` | Nastavak razgovora se pre pretrage prepisuje u samostalno pitanje. |
| `CHUNK_SIZE`, `CHUNK_OVERLAP` | `1000`, `150` | Znakova; važi za nova otpremanja. |
| `VECTOR_STORE` | `qdrant` | `qdrant` ili `pinecone`. |
| `QDRANT_URL`, `QDRANT_COLLECTION` | ugrađen, `pdf_chunks` | Ugrađeni Qdrant drži fajl zaključan, pa radi sa jednim procesom; za više uvicorn workera postavi `QDRANT_URL` na Qdrant server. |
| `PINECONE_API_KEY`, `PINECONE_INDEX` | , `pdf-assistant` | Indeks se pravi sam (serverless, `PINECONE_CLOUD`/`PINECONE_REGION`). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | isključeno | Tracing, vidi niže. |

### Provajderi modela

Sloj za modele je isti kao u document-buddy-ju (`pdf_assistant/ai`): `anthropic`,
`anthropic-foundry`, `openai`, `azure-openai`, `ollama`.

| Kombinacija | Promenljive |
|---|---|
| Claude + OpenAI embedding (podrazumevano) | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` |
| Sve u Microsoft Foundry | `CHAT_PROVIDER=anthropic-foundry`, `CHAT_MODELS=<Claude deploymenti>`, `ANTHROPIC_FOUNDRY_RESOURCE`, `ANTHROPIC_FOUNDRY_API_KEY`; `EMBEDDING_PROVIDER=azure-openai`, `EMBEDDING_MODEL=<deployment>`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| Samo OpenAI | `CHAT_PROVIDER=openai`, `CHAT_MODELS=<modeli>`, `OPENAI_API_KEY` |
| Mešano | `CHAT_MODELS=claude-opus-5-5,openai:gpt-5.1` sa oba ključa |

Na Azure-u je ime modela zapravo ime deploymenta.

Napomene:

- Pitanja i isečci dokumenta idu provajderu modela. Za dokumente koji ne smeju napolje
  koristi se Ollama.
- Na Claude API-ju (ne i na Foundry-ju), za Opus 5.5, Opus 5, Fable 5.1 i Sonnet 5.5,
  uključen je serverski fallback. Ako sigurnosni klasifikator odbije zahtev, isti
  zahtev nastavlja drugi model.

### Pinecone

Svaki PDF dobija svoj imenski prostor (namespace) u jednom indeksu. Pretraga zato ne
treba filter, a brisanje PDF-a je jedan poziv. Za lokalnu probu postoji
[Pinecone Local](https://docs.pinecone.io/guides/operations/local-development). On ne
razume novi format za pravljenje indeksa, pa se indeks napravi REST pozivom, a
`PINECONE_HOST` dobije adresu indeksa. Postupak je u
`backend/tests/test_vectors.py::test_pinecone_local_round_trip`, a test se pokreće sa
`PINECONE_LOCAL_HOST=http://localhost:5080`.

### Supabase (lokalno i cloud)

Supabase može da drži bazu (Postgres) i PDF-ove (Storage), lokalno ili kao projekat na
supabase.com. Kod je isti, menjaju se samo adrese i ključevi. Vektori i dalje idu u
Qdrant ili Pinecone.

**Lokalno** (treba Docker). `supabase/config.toml` u korenu repoa pali samo bazu,
Storage, API i Studio, i pravi privatni bucket `pdfs`:

```bash
npx supabase@2.122.1 start      # u korenu repoa
npx supabase@2.122.1 status     # adrese i ključevi
```

```bash
# backend/.env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
PDF_STORAGE=supabase
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SECRET_KEY=sb_secret_...    # "Secret" iz supabase status
```

Zatim `backend/bin/init.sh` (migracije) i `backend/bin/api.sh`. Studio na
<http://127.0.0.1:54323> pokazuje tabele i otpremljene PDF-ove. Iz Docker kontejnera
umesto `127.0.0.1` ide `host.docker.internal`.

**Cloud** (projekat na supabase.com):

```bash
DATABASE_URL=postgresql://postgres.<ref>:<lozinka>@<session pooler>:5432/postgres
PDF_STORAGE=supabase
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...    # Project Settings → API Keys
```

- `DATABASE_URL` se kopira iz **Connect → Session pooler**:
  - direktna adresa `db.<ref>.supabase.co` radi samo preko IPv6;
  - transaction pooler (port 6543) ne podržava pripremljene upite, a psycopg ih koristi.
- Bucket u cloudu napravi backend pri prvom otpremanju: privatan, samo PDF, do
  `MAX_UPLOAD_MB`.

**Bezbednost.** Supabase sve tabele iz šeme `public` izlaže preko svog REST/GraphQL API-ja
svakome ko ima javni (publishable) ključ. Bez zaštite bi tim ključem moglo da se pročita
`users`, zajedno sa hash-evima lozinki. Zato migracija `0002`:
- na Supabase-u uključuje row level security bez politika;
- ulogama `anon` i `authenticated` oduzima prava.

Proba sa javnim ključem posle migracije vraća `permission denied`. Backend se povezuje
kao vlasnik tabela, pa njega to ne ograničava. Na SQLite-u i običnom Postgres-u
migracija ne radi ništa.

### Tracing (Langfuse)

Kada postoje oba ključa, šalju se dve vrste traga:
- **pitanje:** prepisivanje nastavka razgovora, pretraga i odgovor (sa modelom i
  promptom);
- **obrada PDF-a:** embedding.

Korisnik je Langfuse `user`, a razgovor je `session`. `LANGFUSE_BASE_URL` gađa
sopstveni Langfuse, a bez njega se koristi Langfuse Cloud. Greška u tracingu nikad ne
ruši zahtev.

## Testovi

```bash
backend/bin/check.sh       # ruff, format, mypy --strict, pytest
cd client && npm run check && npm run lint && npm test && npm run build
```

Backend testovi ne idu na mrežu:
- modeli su skriptovani;
- embedder radi po ključnim rečima;
- Qdrant radi u memoriji;
- PDF-ovi se prave u samom testu.

Testovi provajdera rade nad lažnim HTTP transportom.

Skladište ima iste testove za disk i za Supabase. Supabase deo radi nad pravim stackom
kad postoje promenljive (svaki test pravi i briše svoj bucket):

```bash
SUPABASE_TEST_URL=http://127.0.0.1:54321 SUPABASE_TEST_SECRET_KEY=sb_secret_... \
  uv run pytest tests/test_storage.py      # u backend/
```

## Struktura

```
backend/
  src/pdf_assistant/
    api/          FastAPI: auth, pdfs, conversations (+ ocene), main (app, klijent)
    ai/           modeli: interfejsi, OpenAI-kompatibilni, Claude, fabrika
    documents/    čuvanje PDF-a (disk ili Supabase Storage), tekst i isečci, indeksiranje
    chat/         eksperiment (komponente), RAG prompt, razgovori i glasovi
    vectors/      Qdrant i Pinecone iza istog interfejsa
    auth.py       lozinke (bcrypt) i kolačić sesije (JWT)
    tracing.py    Langfuse
    settings.py   sva podešavanja
  alembic/        migracije (0002 zatvara tabele za Supabase Data API)
  tests/
client/           SvelteKit SPA (Svelte 5, Tailwind 4, pdf.js)
supabase/         config.toml za lokalni Supabase (baza + Storage)
docs/demo/        statičan interaktivni demo (GitHub Pages, grana main, folder /docs)
Dockerfile, docker-compose.yml
```

## Šta je promenjeno u odnosu na verziju iz 2024.

Stara verzija:
- je bila Flask + Celery + Redis + LangChain 0.0.352 + OpenAI SDK 0.27 + Pinecone 2;
- je fajlove slala na upload servis sa kursa, a tragove na Langfuse sa kursa;
- nije mogla ni da se pokrene, jer su `app/web/__init__.py` i `app/chat/__init__.py` u
  repou bili kopije drugih fajlova.

Sada:
- FastAPI, SQLAlchemy 2 sa Alembicom, uv, bez LangChaina;
- modeli po izboru (Claude, OpenAI, Foundry, Ollama);
- PDF-ovi na disku ili u Supabase Storage-u, baza SQLite ili Postgres (Supabase lokalno ili cloud);
- Qdrant ili Pinecone;
- Langfuse po izboru;
- Svelte 5 klijent;
- testovi.

Ostali su:
- eksperiment sa ocenama, ispravljen;
- prepisivanje nastavka razgovora;
- PDF pored razgovora.

Šta je u eksperimentu bilo pogrešno:
- **Redis:** API je primao ocenu kao decimalni broj, a upisivao je sa `HINCRBY`, koji
  decimale odbija. Klijent je slao samo 1 i -1, pa to nije puklo, ali bi puklo za
  bilo šta drugo.
- **Glas se nije čuvao uz odgovor:** posle osvežavanja strane isti odgovor je mogao
  da se oceni ponovo, a glas nije mogao da se promeni ni povuče. Sada je jedan glas
  po odgovoru, sačuvan u bazi, i može da se promeni ili povuče.

# Nodal - facial comparison with forensic report

## Run
    python -m venv .venv && source .venv/bin/activate     # Python 3.10 or 3.11 recommended
    pip install -r requirements.txt
    uvicorn backend.main:app --port 8000
Open http://localhost:8000. First start downloads the InsightFace `buffalo_l` model (internet needed once).
If InsightFace fails to load, the app still runs but reports "Inconclusive" because geometry alone cannot support an identity conclusion (see /api/health).

## How it works
- 478 MediaPipe landmarks per face (eyes, brows, nose, lips, contour, irises, cheeks/forehead), Procrustes-aligned.
- ArcFace embedding cosine drives the verbal scale; landmark geometry is supporting evidence and can downgrade a conclusion.
- Quality gates (size, blur, pose, exposure), SHA-256 of every upload, PDF + JSON report, auto-delete after 60 min.

## Before real use
1. Calibrate: edit `COS_CUTS` in `backend/engine.py` using your own labelled same/different pairs. Current values are provisional.
2. Plug in your deepfake detector: `DEEPFAKE_DETECTOR="deepfake_detector:predict"` where `predict(bgr_image) -> float`.
3. Add authentication, HTTPS and rate limiting before exposing it publicly.

## Security setup (new)
**1. Create the first admin (there are no default passwords):**

    python -m backend.manage create-user admin --role admin
    python -m backend.manage create-user alice            # examiner account
Other commands: `set-password`, `delete-user`, `list-users`, `verify-audit`.

**2. HTTPS.** Browsers send login cookies safely only over HTTPS; set `NODAL_HTTPS=1` once you serve over HTTPS (adds Secure cookies and HSTS).
- *Local test (Windows PowerShell):* install mkcert (`choco install mkcert`), then
  `mkcert -install; mkcert localhost`, then
  `$env:NODAL_HTTPS="1"; uvicorn backend.main:app --port 8443 --ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem`
  and open https://localhost:8443.
- *Real server:* put Caddy in front (see `Caddyfile`, automatic certificates) and run
  `NODAL_HTTPS=1 uvicorn backend.main:app --host 127.0.0.1 --proxy-headers --forwarded-allow-ips 127.0.0.1`.
- Plain http://localhost:8000 still works for development (cookie is not marked Secure).

**3. What is protected:** sign-in with scrypt-hashed passwords and 8 h sessions (HttpOnly, SameSite=Strict); lockout after 5 failed logins (15 min); rate limits (login 10/min per IP, comparisons 10/min per user, 240 requests/min per user, 600/min per IP); each case visible only to its owner and admins; security headers incl. a strict Content-Security-Policy.
The rate limiter is in memory, so run a single worker process or move it to Redis. Set `NODAL_SECRET` to a long random value in production (otherwise one is generated in `data/secret.key`).

**4. Audit log.** Sign-ins, comparisons (with image hashes and the verdict, never the images), downloads and deletions are written to a hash-chained log in `data/nodal.db`. Admins see it at `/api/audit`; `python -m backend.manage verify-audit` detects edited or removed entries. Back the file up regularly, since cases themselves auto-delete after 60 minutes.

## Tests and benchmark (new)
    pip install -r requirements-dev.txt
    pytest -q                          # unit + API tests; GitHub Actions runs them on every push (.github/workflows/ci.yml)

**Fixed benchmark pairs** (checks that a change did not make recognition worse):

    python benchmark/make_lfw_pairs.py --lfw-dir path/to/lfw --pairs-txt path/to/pairs.txt   # official LFW pair list
    python -m backend.benchmark --update-baseline    # once, to record today's AUC / EER / FNMR@FMR
    python -m backend.benchmark                       # after every change: exits 1 if AUC or EER got worse
`pytest` runs the same check automatically when `benchmark/pairs.csv` and `baseline.json` exist. The thresholds it prints (`threshold_fmr_1e-3`, etc.) are what you use to calibrate `COS_CUTS`. Add your own realistic pairs to `pairs.csv` (columns `path_a,path_b,label`) to benchmark on your real conditions.

## Desktop app for Windows (new)
No login: on first launch the operator fills in a details form (name, organisation, designation, email, country, purpose, terms). The details stay on the computer (`%LOCALAPPDATA%\Nodal`), appear on every PDF report and in the audit log. A tick-box to share these details with the developer appears only if you set an endpoint, and only those form fields are ever sent (never images, results or hashes). The server listens on 127.0.0.1 only and rejects requests that did not come from the launcher.

Try it without building: `$env:NODAL_MODE="desktop"; uvicorn backend.main:app --port 8000`.

Build the installer: `powershell -File build_windows.ps1` (needs Inno Setup for the .exe installer). To publish on GitHub: `git tag v1.0; git push origin v1.0` and the `release` workflow attaches `Nodal-Setup.exe` to a GitHub Release. To receive opt-in registrations, add a repository secret `NODAL_REGISTRATION_URL` pointing at a write-only webhook or form service (it is visible to anyone who unpacks the app, so never put a secret in it).
Check the licences before distributing: the InsightFace pretrained models are, as far as I know, for non-commercial research use only. Windows will warn about an unsigned installer ("More info", then "Run anyway").

## Android, iPhone and tablets (new): hosted mode
The face engine (MediaPipe, InsightFace, OpenCV) cannot run inside an Android app, so phones use Nodal as a web service you host, installed from the browser:
1. Host it (HTTPS required for install): `docker build -t nodal .` then run the container on a server or a Hugging Face Space (Docker SDK, port 7860). Set secrets `NODAL_SECRET` (long random text) and, to stop strangers using it, `NODAL_INVITE_CODE`.
2. On Android open the address in Chrome, menu, **Install app** (or **Add to Home screen**). It then opens full screen like an app, and the camera or gallery is offered when choosing a photo.
3. Optional Play Store / APK: paste the hosted address into pwabuilder.com and choose Android. That needs the hosted HTTPS address and a Google developer account for the Play Store.
Hosted mode has no passwords: each device registers once with the operator form (details are self-declared and not verified), and each person sees only their own cases. See registrations on the server with `python -m backend.manage list-operators`; the audit log works as before. Free hosts often wipe the disk on restart, which would erase registrations and the audit log, so mount a persistent volume on `NODAL_DATA_DIR` if you need them kept.
Photos from phones are uploaded unchanged (so the hash and ELA stay valid); the limit is 25 MB per image.

## Age-gap safeguard (new)
The face model estimates each person's age (roughly, often several years off). The examiner can also enter the known gap, which takes priority. Provisional rules in `backend/engine.py`: gap of 5+ years moves the verdict one step toward inconclusive; 10+ years means no "different identities" verdict and no "strong" same-identity verdict; 20+ years, or a face estimated under 14, gives "Inconclusive". The geometry cross-check is skipped across age gaps. Age estimates and the cut-offs are uncalibrated, so measure them on your own data.

## Group photo search (new)
Tick "Image A is a group photo", upload the group photo as A and the person's reference as B. Nodal finds every face (up to 80), ranks them by similarity to the reference and draws numbered boxes; the examiner clicks the face to compare, and the normal report is produced for that face (the PDF also shows the group photo with the chosen face marked, how many faces were searched, and that the examiner made the selection). Tiny faces (under about 30 px) can be missed. The group photo is kept at up to 3000 px so faces stay usable; deleting the case also deletes the stored group photo.

## Which face is compared (changed)
If an image contains several faces of similar size, Nodal now refuses to guess and tells the examiner to crop the photo (or, for image A, tick "group photo" and choose the face). The landmark tool and the recognition model always use the same face. The benchmark picks the face nearest the image centre (LFW centres the target person), caches every detected face, and its baseline must be re-recorded once: `python -m backend.benchmark --update-baseline` (about 40 minutes the first time, then rule changes are instant).

## Calibrating the verdict cut-offs (new)
After `python -m backend.benchmark --update-baseline`, run `python -m backend.calibrate` (seconds). It estimates false-match rates from tens of millions of different-person pairs and writes `backend/calibration.json` (strong same = 1 in 100,000 false matches, moderate same = 1 in 1,000, moderate different = below the score 99% of different-person pairs stay under, strong different = below the 0.1th percentile of same-person scores, all moved 0.05 toward inconclusive). The app loads the file at start-up and the PDF states the calibration basis. LFW is easier than most casework, so validate on images like yours before relying on the verdict labels.

## Download and run on Windows (no installer needed)
1. On GitHub click **Code, Download ZIP**, then right-click the zip and **Extract All**.
2. Install **Python 3.11** (from python.org, ticking "Add python.exe to PATH", or from the Microsoft Store). Newer versions such as 3.12 or 3.13 will not work with the face libraries.
3. Double-click **setup_windows.bat** (once; 10 to 20 minutes, needs internet).
4. Double-click **start_nodal.bat**. A small window appears, the first start downloads the face models (about 300 MB, needs internet once), and Nodal opens in your browser. Fill in the operator-details form on first use.
Keep the small window open while you work; closing it stops Nodal. Data is kept in `%LOCALAPPDATA%\Nodal`, and cases are deleted automatically after one hour.

## Hosting on Hugging Face Spaces (free CPU) for phones
1. Create a Space at huggingface.co/new-space, SDK **Docker**, hardware **CPU basic**.
2. `git clone https://huggingface.co/spaces/YOURNAME/nodal D:\nodal-space`, copy the project into it (not `.venv`, `data`, `.git`, `benchmark\pairs.csv` or the cache files), and replace its `README.md` with `deploy/huggingface/README.md` (the Space needs that front matter).
3. In the Space: Settings, Variables and secrets, add secrets `NODAL_SECRET` (long random text) and `NODAL_INVITE_CODE`.
4. `git add . ; git commit -m Nodal ; git push` (use a Hugging Face write token as the password). The first build takes several minutes.
5. Open the direct address `https://YOURNAME-nodal.hf.space` on the phone. The disk resets when the Space restarts, which erases registrations and the audit log.

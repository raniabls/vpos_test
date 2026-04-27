# IZZY React + FastAPI version

This version removes the old `templates/` folder and uses a separate React frontend.
The FastAPI backend logic is kept the same for `/ask`, `/reset`, `/transcribe`, `/admin/offers`, `/admin/prompt`, and `/admin/stats`.

## 1) Backend

From the project root:

```bash
pip install -r requirements.txt
python app.py
```

Backend runs on:

```text
http://127.0.0.1:5000
```

## 2) Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:

```text
http://127.0.0.1:5173
```

## Pages

Chat page:

```text
http://127.0.0.1:5173/
```

Admin page:

```text
http://127.0.0.1:5173/admin
```

## Important

Keep your local `.env` file in the backend root with:

```env
GROQ_API_KEY=your_key_here
```

The React frontend calls the backend through `VITE_API_BASE_URL`. The default is already:

```text
http://127.0.0.1:5000
```

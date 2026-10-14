import { useState, type FormEvent } from "react";

import { api, ApiError } from "../lib/api";
import { toApiError } from "../lib/hooks";
import { fieldErrors, useI18n } from "../lib/i18n";
import type { QuestionAnswer } from "../lib/types";
import { ErrorState, Field, Input, Spinner } from "./ui";

interface Exchange {
  question: string;
  answer: QuestionAnswer;
}

/** Questions about the analysis (FR-18): answered by SALVA's engines, never by free text generation. */
export function AskPanel({ analysisId, simulationId }: { analysisId: string; simulationId: string | null }) {
  const { t, td, lang } = useI18n();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [history, setHistory] = useState<Exchange[]>([]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (q.length < 3) {
      setError(t("ask.tooShort"));
      return;
    }
    setBusy(true);
    setError(undefined);
    setFailure(null);
    try {
      const answer = await api<QuestionAnswer>(`/analyses/${analysisId}/questions`, {
        method: "POST",
        body: { question: q, lang, ...(simulationId ? { simulation_id: simulationId } : {}) },
      });
      setHistory((h) => [{ question: q, answer }, ...h].slice(0, 6));
      setQuestion("");
    } catch (err) {
      const e = toApiError(err);
      const mapped = fieldErrors(e.errors, td);
      if (mapped.question) setError(mapped.question);
      else setFailure(e);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    ask(question);
  };

  const examples = [t("ask.example1"), t("ask.example2"), t("ask.example3"), t("ask.example4")];

  return (
    <section className="panel ask" aria-labelledby="ask-title">
      <h2 id="ask-title">{t("ask.title")}</h2>
      <p className="muted small">{t("ask.intro")}</p>
      <form className="ask__form" onSubmit={submit} noValidate>
        <Field label={t("ask.label")} error={error}>
          {(p) => (
            <Input {...p} value={question} maxLength={300} placeholder={t("ask.placeholder")}
              onChange={(e) => setQuestion(e.target.value)} />
          )}
        </Field>
        <button type="submit" className="button button--primary" disabled={busy}>
          {t("ask.submit")}
        </button>
      </form>
      <div className="chips" role="group" aria-label={t("ask.examples")}>
        {examples.map((example) => (
          <button key={example} type="button" className="chip" disabled={busy} onClick={() => ask(example)}>
            {example}
          </button>
        ))}
      </div>
      {busy && <Spinner label={t("ask.thinking")} />}
      {failure && <ErrorState error={failure} />}
      {history.length > 0 && (
        <ol className="ask__history" aria-live="polite">
          {history.map((item, i) => (
            <li key={`${i}-${item.question}`}>
              <p className="ask__question">{item.question}</p>
              <p className="ask__answer">
                {item.answer.kind === "what_if" && <span className="tag">{t("ask.simulated")}</span>} {item.answer.answer}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// Chat state from typed events (UA-D7) and its rendering. The reply is buffered server-side until it passes
// the checks (UA-D8): `status` events show progress meanwhile, `final` carries the checked reply.
// Rendering only ever sets textContent, so nothing the server sends is interpreted as HTML.

export const initialState = () => ({ status: null, draft: "", citations: [], messages: [], error: null });

export function addUserMessage(state, text) {
  return { ...state, error: null, messages: [...state.messages, { role: "user", text }] };
}

export function reduce(state, { event, data }) {
  switch (event) {
    case "status":
      if (data.code === "stream_expired") {
        return { ...initialState(), status: "Reconnected, showing the conversation so far" };
      }
      return { ...state, status: data.text ?? data.state ?? "Working on it" };
    case "text_delta":
      return { ...state, draft: state.draft + (data.text ?? "") };
    case "citation":
      return { ...state, citations: [...state.citations, data] };
    case "final":
      return {
        ...state,
        status: null,
        draft: "",
        citations: [],
        messages: [...state.messages, {
          role: data.role ?? "assistant",
          text: data.text ?? data.content ?? "",
          citations: state.citations,
        }],
      };
    case "action_card":
      return { ...state, messages: [...state.messages, { role: "card", text: data.title ?? "Action", card: data }] };
    case "handoff":
      return {
        ...state,
        status: null,
        messages: [...state.messages, { role: "system", text: data.text ?? "A specialist will continue here." }],
      };
    case "error":
      return { ...state, status: null, error: data.text ?? "Something went wrong. Please try again." };
    default:
      return state;
  }
}

export function render(state, root, doc = globalThis.document) {
  const element = (tag, className, text) => {
    const node = doc.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const children = state.messages.map((message) => {
    const bubble = element("div", `message ${message.role}`, message.text);
    for (const citation of message.citations ?? []) {
      bubble.appendChild(element("div", "citation", citation.title ?? citation.doc_id ?? "Source"));
    }
    return bubble;
  });
  if (state.draft) children.push(element("div", "message assistant draft", state.draft));
  if (state.status) children.push(element("div", "status", state.status));
  if (state.error) children.push(element("div", "error", state.error));
  root.replaceChildren(...children);
}

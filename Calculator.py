import os
import re
import sqlite3
import tkinter as tk
from decimal import Decimal
from tkinter import font as tkfont

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calculator.db")
OPS = "+−×÷"


# ------------------------------------------------------------------ Database
class HistoryDB:
    def __init__(self, path=DB_PATH):
        self.con = sqlite3.connect(path)
        self.con.execute(
            """CREATE TABLE IF NOT EXISTS history (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   expression TEXT NOT NULL,
                   result TEXT NOT NULL,
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
        )
        self.con.commit()

    def add(self, expression, result):
        self.con.execute(
            "INSERT INTO history (expression, result) VALUES (?, ?)", (expression, result)
        )
        self.con.commit()

    def latest(self, limit=50):
        return self.con.execute(
            "SELECT expression, result FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def clear(self):
        self.con.execute("DELETE FROM history")
        self.con.commit()


# ------------------------------------------------- Safe expression evaluator
# expr   = term (('+'|'-') term)*
# term   = factor (('*'|'/') factor)*
# factor = ('-'|'+') factor | primary '%'*
# primary= NUMBER | '(' expr ')'
TOKEN = re.compile(r"\s*(\d+\.?\d*|\.\d+|[+\-*/()%])")


class CalcError(ValueError):
    pass


class Parser:
    def __init__(self, text):
        text = text.replace("×", "*").replace("÷", "/").replace("−", "-").strip()
        self.tokens, pos = [], 0
        while pos < len(text):
            m = TOKEN.match(text, pos)
            if not m:
                raise CalcError("Invalid expression")
            self.tokens.append(m.group(1))
            pos = m.end()
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        value = self.expr()
        if self.peek() is not None:
            raise CalcError("Invalid expression")
        return value

    def expr(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            op, rhs = self.next(), self.term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def term(self):
        value = self.factor()
        while self.peek() in ("*", "/"):
            op, rhs = self.next(), self.factor()
            if op == "/":
                if rhs == 0:
                    raise CalcError("Can't divide by zero")
                value /= rhs
            else:
                value *= rhs
        return value

    def factor(self):
        if self.peek() in ("+", "-"):
            sign = self.next()
            value = self.factor()
            return -value if sign == "-" else value
        value = self.primary()
        while self.peek() == "%":
            self.next()
            value /= 100
        return value

    def primary(self):
        tok = self.next()
        if tok is None:
            raise CalcError("Incomplete expression")
        if tok == "(":
            value = self.expr()
            if self.next() != ")":
                raise CalcError("Missing )")
            return value
        if re.fullmatch(r"\d+\.?\d*|\.\d+", tok):
            return float(tok)
        raise CalcError("Invalid expression")


def calculate(expression):
    """Returns (cleaned_expression, result_text). Raises CalcError."""
    expression = re.sub(r"[+\-*/×÷−]\s*$", "", expression.strip())
    expression += ")" * max(0, expression.count("(") - expression.count(")"))
    value = Parser(expression).parse()
    if value != value or abs(value) == float("inf"):
        raise CalcError("Result too large")
    text = f"{value:.12g}"
    if "e" in text:
        text = format(Decimal(text), "f")
    return expression, text


# -------------------------------------------------------------------- Themes
THEMES = {
    "light": dict(bg="#e3e6ec", panel="#f6f7fa", ink="#1b1f2a", muted="#6b7385", err="#c0392b",
                  num="#ffffff", num_h="#eceef4", fn="#e9ecf3", fn_h="#dce0ea",
                  op="#3a49a6", op_h="#2f3d8f", eq="#f0a02f", eq_h="#dd8f20",
                  opink="#ffffff", eqink="#2a1c00", sel="#dfe3f5"),
    "dark": dict(bg="#101319", panel="#181c25", ink="#eef0f6", muted="#8f98ad", err="#ff7b6b",
                 num="#222735", num_h="#2c3243", fn="#2b3142", fn_h="#363d52",
                 op="#6f7fe0", op_h="#8391e8", eq="#f0a02f", eq_h="#f7b34f",
                 opink="#0f1330", eqink="#2a1c00", sel="#2c3243"),
}

KEYS = [
    ["AC", "(", ")", "÷"],
    ["7", "8", "9", "×"],
    ["4", "5", "6", "−"],
    ["1", "2", "3", "+"],
    ["%", "0", ".", "="],
]
ROLE = {"AC": "fn", "(": "fn", ")": "fn", "%": "fn", "÷": "op", "×": "op", "−": "op",
        "+": "op", "=": "eq"}


class Key(tk.Label):
    """Flat button built on Label so colours work the same on every OS."""

    def __init__(self, master, text, role, command, font):
        super().__init__(master, text=text, font=font, cursor="hand2", takefocus=0)
        self.role, self.command, self.colors = role, command, None
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<ButtonPress-1>", lambda e: self._paint(hover=True))
        self.bind("<ButtonRelease-1>", self._release)

    def theme(self, colors):
        self.colors = colors
        self._paint()

    def _paint(self, hover=False):
        c = self.colors
        fg = {"op": c["opink"], "eq": c["eqink"]}.get(self.role, c["ink"])
        self.configure(bg=c[self.role + "_h"] if hover else c[self.role], fg=fg)

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._paint(hover=inside)
        if inside:
            self.command()


# ----------------------------------------------------------------------- App
class CalculatorApp:
    def __init__(self, root):
        self.root = root
        self.db = HistoryDB()
        self.expr, self.done, self.dark, self.narrow = "", False, False, None
        root.title("Calculator")
        root.geometry("840x600")
        root.minsize(340, 560)

        self.key_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.expr_font = tkfont.Font(family="Consolas", size=34)
        self.prev_font = tkfont.Font(family="Consolas", size=15)
        self.ui_font = tkfont.Font(family="Segoe UI", size=10)
        self.title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.hist_font = tkfont.Font(family="Consolas", size=12)

        self._build_calculator()
        self._build_history()
        self._bind_keyboard()
        self.root.bind("<Configure>", self._on_root_resize)
        self.apply_theme()
        self.render()
        self.refresh_history()

    # ---- layout
    def _build_calculator(self):
        self.calc = tk.Frame(self.root, padx=16, pady=14)
        bar = tk.Frame(self.calc)
        bar.pack(fill="x")
        self.lbl_title = tk.Label(bar, text="Calculator", font=self.ui_font)
        self.lbl_title.pack(side="left")
        self.btn_theme = self._link(bar, "Theme", self.toggle_theme)
        self.btn_theme.pack(side="right")
        self.btn_del = self._link(bar, "⌫ Delete", lambda: self.press("DEL"))
        self.btn_del.pack(side="right")

        self.screen = tk.Frame(self.calc)
        self.screen.pack(fill="x", pady=(8, 10))
        self.lbl_expr = tk.Label(self.screen, text="0", anchor="e", font=self.expr_font)
        self.lbl_expr.pack(fill="x", pady=(18, 0))
        self.lbl_prev = tk.Label(self.screen, text="", anchor="e", font=self.prev_font)
        self.lbl_prev.pack(fill="x")

        self.pad = tk.Frame(self.calc)
        self.pad.pack(fill="both", expand=True)
        self.keys = []
        for r, row in enumerate(KEYS):
            self.pad.rowconfigure(r, weight=1, uniform="r")
            for c, label in enumerate(row):
                self.pad.columnconfigure(c, weight=1, uniform="c")
                key = Key(self.pad, label, ROLE.get(label, "num"),
                          lambda k=label: self.press(k), self.key_font)
                key.grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
                self.keys.append(key)
        self.pad.bind("<Configure>", self._scale_fonts)

    def _build_history(self):
        self.hist = tk.Frame(self.root, padx=16, pady=14)
        bar = tk.Frame(self.hist)
        bar.pack(fill="x")
        self.lbl_hist = tk.Label(bar, text="History", font=self.title_font)
        self.lbl_hist.pack(side="left")
        self.btn_clear = self._link(bar, "Clear history", self.clear_history)
        self.btn_clear.pack(side="right")
        body = tk.Frame(self.hist)
        body.pack(fill="both", expand=True, pady=(8, 0))
        self.scroll = tk.Scrollbar(body)
        self.scroll.pack(side="right", fill="y")
        self.listbox = tk.Listbox(body, font=self.hist_font, bd=0, highlightthickness=0,
                                  activestyle="none", yscrollcommand=self.scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.scroll.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._use_history)
        self._rows = []

    def _link(self, parent, text, command):
        lbl = tk.Label(parent, text=text, font=self.ui_font, cursor="hand2", padx=6)
        lbl.bind("<Button-1>", lambda e: command())
        return lbl

    def _place_panels(self, narrow):
        self.narrow = narrow
        for w in (self.calc, self.hist):
            w.grid_forget()
        for i in range(2):
            self.root.columnconfigure(i, weight=0, minsize=0)
            self.root.rowconfigure(i, weight=0, minsize=0)
        if narrow:
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=4)
            self.root.rowconfigure(1, weight=1, minsize=120)
            self.calc.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
            self.hist.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        else:
            self.root.rowconfigure(0, weight=1)
            self.root.columnconfigure(0, weight=3, minsize=340)
            self.root.columnconfigure(1, weight=2, minsize=240)
            self.calc.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=14)
            self.hist.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=14)

    def _on_root_resize(self, event):
        if event.widget is self.root:
            narrow = event.width < 640
            if narrow != self.narrow:
                self._place_panels(narrow)

    def _scale_fonts(self, event):
        cell = min(event.width / 4, event.height / 5)
        self.key_font.configure(size=max(11, int(cell / 3.6)))
        self._fit_display()

    def _fit_display(self):
        base = max(20, min(40, int(self.root.winfo_width() / 22)))
        shrink = max(0, len(self.expr) - 10)
        self.expr_font.configure(size=max(14, base - shrink))

    # ---- theme
    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()

    def apply_theme(self):
        c = THEMES["dark" if self.dark else "light"]
        self.c = c
        self.root.configure(bg=c["bg"])
        for panel in (self.calc, self.hist):
            panel.configure(bg=c["panel"])
            for child in panel.winfo_children():
                self._paint_tree(child, c)
        for key in self.keys:
            key.theme(c)
        self.lbl_expr.configure(bg=c["panel"], fg=c["ink"])
        self.lbl_prev.configure(bg=c["panel"], fg=c["muted"])
        self.listbox.configure(bg=c["panel"], fg=c["ink"], selectbackground=c["sel"],
                               selectforeground=c["ink"])
        self.lbl_hist.configure(fg=c["ink"])
        for link in (self.btn_theme, self.btn_del, self.btn_clear, self.lbl_title):
            link.configure(fg=c["muted"])

    def _paint_tree(self, widget, c):
        if isinstance(widget, (Key, tk.Listbox, tk.Scrollbar)):
            return
        widget.configure(bg=c["panel"])
        for child in widget.winfo_children():
            self._paint_tree(child, c)

    # ---- input handling
    def _bind_keyboard(self):
        keymap = {"*": "×", "/": "÷", "-": "−", "x": "×", "X": "×"}

        def on_key(e):
            ch = e.char
            if ch and re.fullmatch(r"[0-9.+()%]", ch):
                self.press(ch)
            elif ch in keymap:
                self.press(keymap[ch])
            elif e.keysym in ("Return", "KP_Enter") or ch == "=":
                self.press("=")
            elif e.keysym == "BackSpace":
                self.press("DEL")
            elif e.keysym in ("Escape", "Delete"):
                self.press("AC")

        self.root.bind("<Key>", on_key)

    def press(self, k):
        last = self.expr[-1:]
        is_value_end = bool(re.fullmatch(r"[\d)%]", last))
        if k.isdigit():
            self._start_fresh_if_done()
            if re.fullmatch(r"[)%]", last):
                self.expr += "×"
            self.expr += k
        elif k == ".":
            self._start_fresh_if_done()
            if re.fullmatch(r"[)%]", self.expr[-1:]):
                self.expr += "×"
            segment = re.split(r"[+−×÷()%]", self.expr)[-1]
            if "." in segment:
                return
            self.expr += "0." if segment == "" else "."
        elif k in OPS:
            self.done = False
            if not self.expr:
                if k == "−":
                    self.expr = "−"
            elif self.expr == "−":
                return
            elif last == "(" and k != "−":
                return
            elif last in OPS:
                self.expr = self.expr[:-1] + k
            else:
                self.expr += k
        elif k == "%":
            if is_value_end:
                self.expr += "%"
                self.done = False
        elif k == "(":
            self._start_fresh_if_done()
            if is_value_end and not self.done:
                self.expr += "×"
            self.expr += "("
        elif k == ")":
            if self.expr.count("(") > self.expr.count(")") and is_value_end:
                self.expr += ")"
        elif k == "AC":
            self.expr, self.done = "", False
        elif k == "DEL":
            self.expr = "" if self.done else self.expr[:-1]
            self.done = False
        elif k == "=":
            return self.equals()
        self.render()

    def _start_fresh_if_done(self):
        if self.done:
            self.expr, self.done = "", False

    # ---- display
    def render(self):
        self.lbl_expr.configure(text=self.expr or "0")
        self._fit_display()
        self.lbl_prev.configure(text="", fg=self.c["muted"], font=self.prev_font)
        body = self.expr[1:] if self.expr.startswith("−") else self.expr
        if self.expr and not self.done and re.search(r"[+−×÷%]", body):
            try:
                self.lbl_prev.configure(text="= " + calculate(self.expr)[1])
            except CalcError:
                pass

    def equals(self):
        if not self.expr or self.done:
            return
        try:
            cleaned, result = calculate(self.expr)
        except CalcError as err:
            self.lbl_prev.configure(text=str(err), fg=self.c["err"], font=self.ui_font)
            return
        self.db.add(cleaned, result)
        self.expr, self.done = result.replace("-", "−"), True
        self.lbl_expr.configure(text=self.expr)
        self._fit_display()
        self.lbl_prev.configure(text=cleaned + " =", fg=self.c["muted"], font=self.prev_font)
        self.refresh_history()

    # ---- history
    def refresh_history(self):
        self._rows = self.db.latest()
        self.listbox.delete(0, "end")
        if not self._rows:
            self.listbox.insert("end", "Your calculations will appear here.")
            return
        for expression, result in self._rows:
            self.listbox.insert("end", f"{expression} = {result}")

    def _use_history(self, _event):
        sel = self.listbox.curselection()
        if sel and self._rows:
            self.expr, self.done = self._rows[sel[0]][1].replace("-", "−"), True
            self.render()

    def clear_history(self):
        self.db.clear()
        self.refresh_history()


def main():
    root = tk.Tk()
    CalculatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
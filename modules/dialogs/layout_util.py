"""Size small dialogs from their content rather than fixed pixel assumptions."""


def responsive_button_grid(frame, buttons, maximum_columns=4):
    """Keep complete button labels visible without inflating the parent pane."""
    natural_width = max(button.winfo_reqwidth() for button in buttons) + 6
    for button in buttons:
        button.configure(width=1)
    previous_columns = None

    def arrange(width):
        nonlocal previous_columns
        columns = max(1, min(maximum_columns, width // natural_width))
        if columns == previous_columns:
            return
        previous_columns = columns
        for column in range(maximum_columns):
            frame.columnconfigure(column, weight=1 if column < columns else 0,
                                  uniform="actions" if column < columns else "")
        for index, button in enumerate(buttons):
            row, column = divmod(index, columns)
            button.grid(row=row, column=column, sticky="ew", pady=3,
                        padx=(0 if column == 0 else 3, 0 if column == columns - 1 else 3))

    # Start compactly; Configure uses the actual space allocated by the parent.
    arrange(natural_width * min(3, maximum_columns))
    frame.bind("<Configure>", lambda event: arrange(event.width), add="+")


def fit_dialog(dialog, parent, minimum_width=440, minimum_height=240):
    dialog.update_idletasks()
    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    width = min(max(minimum_width, dialog.winfo_reqwidth()), max(320, screen_width - 60))
    height = min(max(minimum_height, dialog.winfo_reqheight()), max(240, screen_height - 100))
    x = max(0, min(parent.winfo_x() + (parent.winfo_width() - width) // 2, screen_width - width))
    y = max(0, min(parent.winfo_y() + (parent.winfo_height() - height) // 2, screen_height - height - 50))
    dialog.resizable(True, True)
    dialog.minsize(width, height)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

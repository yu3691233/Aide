package cc.aidelink.app.ui.screens.idechat

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle

class TerminalEmulator(initialCols: Int = 80, initialRows: Int = 24) {

    data class Cell(
        var ch: Char = ' ',
        var fg: Color? = null,
        var bg: Color? = null,
        var bold: Boolean = false,
        var reverse: Boolean = false,
        var underline: Boolean = false,
        var italic: Boolean = false,
    ) {
        fun reset() {
            ch = ' '; fg = null; bg = null; bold = false; reverse = false
            underline = false; italic = false
        }

        fun copyFrom(other: Cell) {
            ch = other.ch; fg = other.fg; bg = other.bg; bold = other.bold
            reverse = other.reverse; underline = other.underline; italic = other.italic
        }
    }

    var cols: Int = initialCols
        private set
    var rows: Int = initialRows
        private set

    private var mainScreen: Array<Array<Cell>> = makeScreen(rows, cols)
    private var altScreen: Array<Array<Cell>> = makeScreen(rows, cols)
    private var screen: Array<Array<Cell>> = mainScreen
    private var onAltScreen = false

    var cursorRow: Int = 0
        private set
    var cursorCol: Int = 0
        private set

    private var topMargin: Int = 0
    private var bottomMargin: Int = rows

    private data class SavedState(
        var row: Int = 0,
        var col: Int = 0,
        var fg: Color? = null,
        var bg: Color? = null,
        var bold: Boolean = false,
        var reverse: Boolean = false,
        var underline: Boolean = false,
        var italic: Boolean = false,
        var useLineDrawingG0: Boolean = false,
        var useLineDrawingG1: Boolean = false,
        var useG0: Boolean = true,
    )

    private var savedMain = SavedState()
    private var savedAlt = SavedState()

    private var attrFg: Color? = null
    private var attrBg: Color? = null
    private var attrBold: Boolean = false
    private var attrReverse: Boolean = false
    private var attrUnderline: Boolean = false
    private var attrItalic: Boolean = false

    private var aboutToAutoWrap = false

    private var useLineDrawingG0 = false
    private var useLineDrawingG1 = false
    private var useG0 = true

    var cursorKeysApplicationMode = false
        private set

    private var escState = EscState.NORMAL
    private val escParams = StringBuilder()

    private val scrollback = mutableListOf<Array<Cell>>()
    private val maxScrollback = 500

    var version: Long = 0L
        private set

    private enum class EscState {
        NORMAL, ESC, CSI, OSC, ESC_SELECT_G0, ESC_SELECT_G1, ESC_SKIP1,
    }

    @Synchronized
    fun process(data: String) {
        for (ch in data) {
            processChar(ch)
        }
        version++
    }

    @Synchronized
    fun resize(newCols: Int, newRows: Int) {
        if (newCols <= 0 || newRows <= 0) return
        if (newCols == cols && newRows == rows) return

        mainScreen = resizeScreen(mainScreen, rows, cols, newRows, newCols)
        altScreen = resizeScreen(altScreen, rows, cols, newRows, newCols)
        screen = if (onAltScreen) altScreen else mainScreen

        cols = newCols
        rows = newRows
        topMargin = 0
        bottomMargin = rows
        cursorRow = cursorRow.coerceIn(0, rows - 1)
        cursorCol = cursorCol.coerceIn(0, cols - 1)
        aboutToAutoWrap = false
        version++
    }

    @Synchronized
    fun reset() {
        screen = mainScreen
        onAltScreen = false
        clearScreenCells(mainScreen)
        clearScreenCells(altScreen)
        cursorRow = 0
        cursorCol = 0
        topMargin = 0
        bottomMargin = rows
        attrFg = null; attrBg = null; attrBold = false; attrReverse = false
        attrUnderline = false; attrItalic = false
        aboutToAutoWrap = false
        useLineDrawingG0 = false; useLineDrawingG1 = false; useG0 = true
        cursorKeysApplicationMode = false
        escState = EscState.NORMAL
        escParams.clear()
        oscEscSeen = false
        savedMain = SavedState()
        savedAlt = SavedState()
        scrollback.clear()
        version++
    }

    @Synchronized
    fun totalRowsWithScrollback(): Int = scrollback.size + rows

    @Synchronized
    fun maxScrollbackOffset(windowRows: Int): Int {
        if (windowRows <= 0) return 0
        return (totalRowsWithScrollback() - windowRows).coerceAtLeast(0)
    }

    @Synchronized
    fun render(scrollbackOffsetRows: Int = 0, windowRows: Int = rows): AnnotatedString {
        val defaultFg = Color(0xFFD3D7CF)
        val defaultBg = Color.Black
        val visibleRows = resolveVisibleRows(scrollbackOffsetRows, windowRows)

        return buildAnnotatedString {
            for (r in visibleRows.indices) {
                val row = visibleRows[r]
                var runStart = 0
                while (runStart < cols) {
                    val refCell = cellAt(row, runStart)
                    val sb = StringBuilder()
                    sb.append(refCell.ch)
                    var runEnd = runStart + 1
                    while (runEnd < cols) {
                        val nextCell = cellAt(row, runEnd)
                        if (!sameStyle(nextCell, refCell)) break
                        sb.append(nextCell.ch)
                        runEnd++
                    }
                    val effFg: Color
                    val effBg: Color
                    if (refCell.reverse) {
                        effFg = refCell.bg ?: defaultBg
                        effBg = refCell.fg ?: defaultFg
                    } else {
                        effFg = refCell.fg ?: Color.Unspecified
                        effBg = refCell.bg ?: Color.Unspecified
                    }
                    withStyle(SpanStyle(
                        color = effFg,
                        background = if (effBg != Color.Unspecified) effBg else Color.Unspecified,
                        fontWeight = if (refCell.bold) FontWeight.SemiBold else FontWeight.Normal,
                    )) {
                        append(sb.toString())
                    }
                    runStart = runEnd
                }

                if (r < visibleRows.lastIndex) append('\n')
            }
        }
    }

    @Synchronized
    fun renderSelectionText(scrollbackOffsetRows: Int = 0, windowRows: Int = rows): String {
        val visibleRows = resolveVisibleRows(scrollbackOffsetRows, windowRows)
        if (visibleRows.isEmpty()) return ""

        val out = StringBuilder()
        for (r in visibleRows.indices) {
            val row = visibleRows[r]
            val lineChars = CharArray(cols)
            for (c in 0 until cols) {
                lineChars[c] = cellAt(row, c).ch
            }
            out.append(String(lineChars).trimEnd(' '))
            if (r < visibleRows.lastIndex) out.append('\n')
        }
        return out.toString()
    }

    data class TerminalRun(
        val col: Int,
        val text: String,
        val fg: Color,
        val bg: Color,
        val bold: Boolean,
        val italic: Boolean,
        val underline: Boolean,
    )

    @Synchronized
    fun renderRuns(scrollbackOffsetRows: Int = 0, windowRows: Int = rows): List<List<TerminalRun>> {
        val defaultFg = Color(0xFFD3D7CF)
        val defaultBg = Color.Black
        val visibleRows = resolveVisibleRows(scrollbackOffsetRows, windowRows)

        val result = ArrayList<List<TerminalRun>>(visibleRows.size)
        for (r in visibleRows.indices) {
            val row = visibleRows[r]
            val runs = mutableListOf<TerminalRun>()
            var runStart = 0
            while (runStart < cols) {
                val refCell = cellAt(row, runStart)
                val sb = StringBuilder()
                sb.append(refCell.ch)
                var runEnd = runStart + 1
                while (runEnd < cols) {
                    val nextCell = cellAt(row, runEnd)
                    if (!sameStyle(nextCell, refCell)) break
                    sb.append(nextCell.ch)
                    runEnd++
                }
                val effFg: Color
                val effBg: Color
                if (refCell.reverse) {
                    effFg = refCell.bg ?: defaultBg
                    effBg = refCell.fg ?: defaultFg
                } else {
                    effFg = refCell.fg ?: defaultFg
                    effBg = refCell.bg ?: Color.Unspecified
                }
                runs.add(TerminalRun(
                    col = runStart,
                    text = sb.toString(),
                    fg = effFg,
                    bg = effBg,
                    bold = refCell.bold,
                    italic = refCell.italic,
                    underline = refCell.underline,
                ))
                runStart = runEnd
            }
            result.add(runs)
        }
        return result
    }

    @Synchronized
    fun getCursorPosition(): Pair<Int, Int> = cursorRow to cursorCol

    @Synchronized
    fun getCursorPositionInWindow(scrollbackOffsetRows: Int = 0, windowRows: Int = rows): Pair<Int, Int>? {
        val rowCount = windowRows.coerceAtLeast(1)
        val totalRows = scrollback.size + rows
        val maxOffset = (totalRows - rowCount).coerceAtLeast(0)
        val offset = scrollbackOffsetRows.coerceIn(0, maxOffset)
        val startRow = (totalRows - rowCount - offset).coerceAtLeast(0)

        val absoluteCursorRow = scrollback.size + cursorRow
        val visibleCursorRow = absoluteCursorRow - startRow
        if (visibleCursorRow !in 0 until rowCount) return null
        return visibleCursorRow to cursorCol
    }

    private fun processChar(ch: Char) {
        when (escState) {
            EscState.NORMAL -> processNormal(ch)
            EscState.ESC -> processEsc(ch)
            EscState.CSI -> processCsi(ch)
            EscState.OSC -> processOsc(ch)
            EscState.ESC_SELECT_G0 -> {
                useLineDrawingG0 = (ch == '0')
                escState = EscState.NORMAL
            }
            EscState.ESC_SELECT_G1 -> {
                useLineDrawingG1 = (ch == '0')
                escState = EscState.NORMAL
            }
            EscState.ESC_SKIP1 -> {
                escState = EscState.NORMAL
            }
        }
    }

    private fun processNormal(ch: Char) {
        when (ch) {
            '\u001B' -> { escState = EscState.ESC }
            '\r' -> { cursorCol = 0; aboutToAutoWrap = false }
            '\n', '\u000B', '\u000C' -> { doLinefeed() }
            '\t' -> {
                aboutToAutoWrap = false
                val nextTab = ((cursorCol / 8) + 1) * 8
                cursorCol = nextTab.coerceAtMost(cols - 1)
            }
            '\b' -> { aboutToAutoWrap = false; if (cursorCol > 0) cursorCol-- }
            '\u0007' -> { /* Bell */ }
            '\u000E', '\u000F' -> { useG0 = (ch == '\u000F') }
            else -> {
                if (ch.code < 32) return
                emitChar(ch)
            }
        }
    }

    private fun processEsc(ch: Char) {
        escState = EscState.NORMAL
        when (ch) {
            '[' -> { escState = EscState.CSI; escParams.clear() }
            ']' -> { escState = EscState.OSC; escParams.clear() }
            '7' -> saveCursor()
            '8' -> restoreCursor()
            'D' -> doLinefeed()
            'E' -> { cursorCol = 0; doLinefeed() }
            'M' -> doReverseIndex()
            'c' -> reset()
            '(' -> { escState = EscState.ESC_SELECT_G0 }
            ')' -> { escState = EscState.ESC_SELECT_G1 }
            '*', '+' -> { escState = EscState.ESC_SKIP1 }
            '#' -> { escState = EscState.ESC_SKIP1 }
            '>' -> { /* DECKPNM */ }
            '=' -> { /* DECKPAM */ }
        }
    }

    private fun processCsi(ch: Char) {
        if (ch in '0'..'9' || ch == ';' || ch == '?' || ch == '>' || ch == '!' || ch == ' ' || ch == '"' || ch == '\'') {
            escParams.append(ch)
            return
        }
        escState = EscState.NORMAL
        val paramsStr = escParams.toString()
        val privateMode = paramsStr.startsWith("?")
        val numStr = if (privateMode) paramsStr.drop(1) else paramsStr
        val params = if (numStr.isBlank()) emptyList() else numStr.split(';').map { it.toIntOrNull() ?: 0 }

        when (ch) {
            'm' -> applySgr(paramsStr)
            'H', 'f' -> {
                val targetRow = (params.getOrNull(0) ?: 1).coerceAtLeast(1) - 1
                val targetCol = (params.getOrNull(1) ?: 1).coerceAtLeast(1) - 1
                cursorRow = targetRow.coerceIn(0, rows - 1)
                cursorCol = targetCol.coerceIn(0, cols - 1)
                aboutToAutoWrap = false
            }
            'A' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorRow = (cursorRow - n).coerceAtLeast(0); aboutToAutoWrap = false }
            'B' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorRow = (cursorRow + n).coerceIn(0, rows - 1); aboutToAutoWrap = false }
            'C' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorCol = (cursorCol + n).coerceIn(0, cols - 1); aboutToAutoWrap = false }
            'D' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorCol = (cursorCol - n).coerceAtLeast(0); aboutToAutoWrap = false }
            'E' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorRow = (cursorRow + n).coerceIn(0, rows - 1); cursorCol = 0; aboutToAutoWrap = false }
            'F' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); cursorRow = (cursorRow - n).coerceAtLeast(0); cursorCol = 0; aboutToAutoWrap = false }
            'G' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1) - 1; cursorCol = n.coerceIn(0, cols - 1); aboutToAutoWrap = false }
            'd' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1) - 1; cursorRow = n.coerceIn(0, rows - 1); aboutToAutoWrap = false }
            'J' -> doEraseInDisplay(params.getOrNull(0) ?: 0)
            'K' -> doEraseInLine(params.getOrNull(0) ?: 0)
            'L' -> doInsertLines((params.getOrNull(0) ?: 1).coerceAtLeast(1))
            'M' -> doDeleteLines((params.getOrNull(0) ?: 1).coerceAtLeast(1))
            'S' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); repeat(n) { scrollUp() } }
            'T' -> { if (params.size <= 1) { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); repeat(n) { scrollDown() } } }
            'P' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); doDeleteChars(n) }
            '@' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); doInsertChars(n) }
            'X' -> { val n = (params.getOrNull(0) ?: 1).coerceAtLeast(1); doEraseChars(n) }
            'r' -> {
                val top = (params.getOrNull(0) ?: 1).coerceAtLeast(1) - 1
                val bot = (params.getOrNull(1) ?: rows)
                topMargin = top.coerceIn(0, rows - 2)
                bottomMargin = bot.coerceIn(topMargin + 2, rows)
                cursorRow = 0; cursorCol = 0; aboutToAutoWrap = false
            }
            's' -> { if (!privateMode) saveCursor() }
            'u' -> restoreCursor()
            'h' -> { if (privateMode) doDecSet(params, true) }
            'l' -> { if (privateMode) doDecSet(params, false) }
            'p' -> {
                if (paramsStr.contains("!")) {
                    topMargin = 0; bottomMargin = rows
                    attrFg = null; attrBg = null; attrBold = false; attrReverse = false
                    attrUnderline = false; attrItalic = false; aboutToAutoWrap = false
                }
            }
        }
    }

    private var oscEscSeen = false

    private fun processOsc(ch: Char) {
        if (oscEscSeen) {
            oscEscSeen = false
            if (ch == '\\') {
                escState = EscState.NORMAL; escParams.clear(); return
            }
            escState = EscState.ESC; escParams.clear(); processEsc(ch); return
        }
        if (ch == '\u0007') { escState = EscState.NORMAL; escParams.clear(); return }
        if (ch == '\u001B') { oscEscSeen = true; return }
        if (escParams.length < 256) escParams.append(ch)
    }

    private fun emitChar(ch: Char) {
        if (aboutToAutoWrap) {
            aboutToAutoWrap = false; cursorCol = 0
            if (cursorRow + 1 >= bottomMargin) scrollUp() else cursorRow++
        }
        val mapped = if (if (useG0) useLineDrawingG0 else useLineDrawingG1) mapLineDrawing(ch) else ch
        val cell = screen[cursorRow][cursorCol]
        cell.ch = mapped; cell.fg = attrFg; cell.bg = attrBg; cell.bold = attrBold
        cell.reverse = attrReverse; cell.underline = attrUnderline; cell.italic = attrItalic
        if (cursorCol + 1 >= cols) aboutToAutoWrap = true else cursorCol++
    }

    private fun doLinefeed() {
        aboutToAutoWrap = false
        val belowScrollRegion = cursorRow >= bottomMargin
        if (belowScrollRegion) {
            if (cursorRow < rows - 1) cursorRow++
        } else {
            val newRow = cursorRow + 1
            if (newRow >= bottomMargin) scrollUp() else cursorRow = newRow
        }
    }

    private fun doReverseIndex() {
        aboutToAutoWrap = false
        if (cursorRow <= topMargin) scrollDown() else cursorRow--
    }

    private fun scrollUp() {
        if (!onAltScreen && topMargin == 0) {
            val saved = Array(cols) { Cell() }
            for (c in 0 until cols) saved[c].copyFrom(screen[topMargin][c])
            scrollback.add(saved)
            if (scrollback.size > maxScrollback) scrollback.removeAt(0)
        }
        for (r in topMargin until bottomMargin - 1) {
            for (c in 0 until cols) screen[r][c].copyFrom(screen[r + 1][c])
        }
        for (c in 0 until cols) blankCell(screen[bottomMargin - 1][c])
    }

    private fun scrollDown() {
        for (r in bottomMargin - 1 downTo topMargin + 1) {
            for (c in 0 until cols) screen[r][c].copyFrom(screen[r - 1][c])
        }
        for (c in 0 until cols) blankCell(screen[topMargin][c])
    }

    private fun doInsertLines(count: Int) {
        aboutToAutoWrap = false
        if (cursorRow < topMargin || cursorRow >= bottomMargin) return
        val linesAfter = bottomMargin - cursorRow
        val toInsert = count.coerceAtMost(linesAfter)
        for (r in bottomMargin - 1 downTo cursorRow + toInsert) {
            for (c in 0 until cols) screen[r][c].copyFrom(screen[r - toInsert][c])
        }
        for (r in cursorRow until cursorRow + toInsert) {
            for (c in 0 until cols) blankCell(screen[r][c])
        }
    }

    private fun doDeleteLines(count: Int) {
        aboutToAutoWrap = false
        if (cursorRow < topMargin || cursorRow >= bottomMargin) return
        val linesAfter = bottomMargin - cursorRow
        val toDelete = count.coerceAtMost(linesAfter)
        val toMove = linesAfter - toDelete
        for (r in cursorRow until cursorRow + toMove) {
            for (c in 0 until cols) screen[r][c].copyFrom(screen[r + toDelete][c])
        }
        for (r in cursorRow + toMove until bottomMargin) {
            for (c in 0 until cols) blankCell(screen[r][c])
        }
    }

    private fun doInsertChars(count: Int) {
        aboutToAutoWrap = false
        val n = count.coerceAtMost(cols - cursorCol)
        for (c in cols - 1 downTo cursorCol + n) screen[cursorRow][c].copyFrom(screen[cursorRow][c - n])
        for (c in cursorCol until (cursorCol + n).coerceAtMost(cols)) blankCell(screen[cursorRow][c])
    }

    private fun doDeleteChars(count: Int) {
        aboutToAutoWrap = false
        val n = count.coerceAtMost(cols - cursorCol)
        for (c in cursorCol until cols - n) screen[cursorRow][c].copyFrom(screen[cursorRow][c + n])
        for (c in cols - n until cols) blankCell(screen[cursorRow][c])
    }

    private fun doEraseChars(count: Int) {
        aboutToAutoWrap = false
        val n = count.coerceAtMost(cols - cursorCol)
        for (c in cursorCol until cursorCol + n) blankCell(screen[cursorRow][c])
    }

    private fun doEraseInDisplay(mode: Int) {
        aboutToAutoWrap = false
        when (mode) {
            0 -> {
                for (c in cursorCol until cols) blankCell(screen[cursorRow][c])
                for (r in cursorRow + 1 until rows) for (c in 0 until cols) blankCell(screen[r][c])
            }
            1 -> {
                for (r in 0 until cursorRow) for (c in 0 until cols) blankCell(screen[r][c])
                for (c in 0..cursorCol.coerceAtMost(cols - 1)) blankCell(screen[cursorRow][c])
            }
            2 -> {
                for (r in 0 until rows) for (c in 0 until cols) blankCell(screen[r][c])
            }
            3 -> scrollback.clear()
        }
    }

    private fun doEraseInLine(mode: Int) {
        aboutToAutoWrap = false
        when (mode) {
            0 -> { for (c in cursorCol until cols) blankCell(screen[cursorRow][c]) }
            1 -> { for (c in 0..cursorCol.coerceAtMost(cols - 1)) blankCell(screen[cursorRow][c]) }
            2 -> { for (c in 0 until cols) blankCell(screen[cursorRow][c]) }
        }
    }

    private fun doDecSet(params: List<Int>, enable: Boolean) {
        for (p in params) {
            when (p) {
                47, 1047, 1049 -> {
                    if (enable) {
                        if (!onAltScreen) { saveCursor(); onAltScreen = true; screen = altScreen; clearScreenCells(altScreen); topMargin = 0; bottomMargin = rows }
                    } else {
                        if (onAltScreen) { onAltScreen = false; screen = mainScreen; restoreCursor(); topMargin = 0; bottomMargin = rows }
                    }
                }
                1 -> cursorKeysApplicationMode = enable
            }
        }
    }

    private fun saveCursor() {
        val state = if (onAltScreen) savedAlt else savedMain
        state.row = cursorRow; state.col = cursorCol; state.fg = attrFg; state.bg = attrBg
        state.bold = attrBold; state.reverse = attrReverse; state.underline = attrUnderline
        state.italic = attrItalic; state.useLineDrawingG0 = useLineDrawingG0
        state.useLineDrawingG1 = useLineDrawingG1; state.useG0 = useG0
    }

    private fun restoreCursor() {
        val state = if (onAltScreen) savedAlt else savedMain
        cursorRow = state.row.coerceIn(0, rows - 1); cursorCol = state.col.coerceIn(0, cols - 1)
        attrFg = state.fg; attrBg = state.bg; attrBold = state.bold; attrReverse = state.reverse
        attrUnderline = state.underline; attrItalic = state.italic
        useLineDrawingG0 = state.useLineDrawingG0; useLineDrawingG1 = state.useLineDrawingG1
        useG0 = state.useG0; aboutToAutoWrap = false
    }

    private fun applySgr(paramsStr: String) {
        val raw = if (paramsStr.isBlank()) "0" else paramsStr
        val parts = raw.split(';').map { it.toIntOrNull() ?: 0 }
        var i = 0
        while (i < parts.size) {
            when (parts[i]) {
                0 -> { attrFg = null; attrBg = null; attrBold = false; attrReverse = false; attrUnderline = false; attrItalic = false }
                1 -> attrBold = true
                3 -> attrItalic = true
                4 -> attrUnderline = true
                7 -> attrReverse = true
                22 -> attrBold = false
                23 -> attrItalic = false
                24 -> attrUnderline = false
                27 -> attrReverse = false
                in 30..37 -> attrFg = ansiColor(parts[i] - 30)
                38 -> { val result = parseExtendedColor(parts, i + 1); if (result != null) { attrFg = result.first; i = result.second; i++; continue } }
                39 -> attrFg = null
                in 40..47 -> attrBg = ansiColor(parts[i] - 40)
                48 -> { val result = parseExtendedColor(parts, i + 1); if (result != null) { attrBg = result.first; i = result.second; i++; continue } }
                49 -> attrBg = null
                in 90..97 -> attrFg = ansiColor((parts[i] - 90) + 8)
                in 100..107 -> attrBg = ansiColor((parts[i] - 100) + 8)
            }
            i++
        }
    }

    private fun parseExtendedColor(parts: List<Int>, startIndex: Int): Pair<Color, Int>? {
        if (startIndex >= parts.size) return null
        return when (parts[startIndex]) {
            5 -> {
                if (startIndex + 1 >= parts.size) return null
                val n = parts[startIndex + 1]
                Pair(color256(n), startIndex + 1)
            }
            2 -> {
                if (startIndex + 3 >= parts.size) return null
                val r = parts[startIndex + 1].coerceIn(0, 255)
                val g = parts[startIndex + 2].coerceIn(0, 255)
                val b = parts[startIndex + 3].coerceIn(0, 255)
                Pair(Color(r, g, b), startIndex + 3)
            }
            else -> null
        }
    }

    private fun mapLineDrawing(ch: Char): Char {
        return when (ch) {
            '_' -> ' '; '`' -> '\u25C6'; '0' -> '\u2588'; 'a' -> '\u2592'
            'b' -> '\u2409'; 'c' -> '\u240C'; 'd' -> '\u240D'; 'e' -> '\u240A'
            'f' -> '\u00B0'; 'g' -> '\u00B1'; 'h' -> '\u2424'; 'i' -> '\u240B'
            'j' -> '\u2518'; 'k' -> '\u2510'; 'l' -> '\u250C'; 'm' -> '\u2514'
            'n' -> '\u253C'; 'o' -> '\u23BA'; 'p' -> '\u23BB'; 'q' -> '\u2500'
            'r' -> '\u23BC'; 's' -> '\u23BD'; 't' -> '\u251C'; 'u' -> '\u2524'
            'v' -> '\u2534'; 'w' -> '\u252C'; 'x' -> '\u2502'; 'y' -> '\u2264'
            'z' -> '\u2265'; '{' -> '\u03C0'; '|' -> '\u2260'; '}' -> '\u00A3'
            '~' -> '\u00B7'; else -> ch
        }
    }

    private fun blankCell(cell: Cell) {
        cell.ch = ' '; cell.fg = attrFg; cell.bg = attrBg; cell.bold = attrBold
        cell.reverse = attrReverse; cell.underline = attrUnderline; cell.italic = attrItalic
    }

    private fun sameStyle(a: Cell, b: Cell): Boolean {
        return a.fg == b.fg && a.bg == b.bg && a.bold == b.bold &&
                a.reverse == b.reverse && a.underline == b.underline && a.italic == b.italic
    }

    private fun resolveVisibleRows(scrollbackOffsetRows: Int, windowRows: Int): List<Array<Cell>> {
        val allRows = ArrayList<Array<Cell>>(scrollback.size + rows)
        allRows.addAll(scrollback)
        for (r in 0 until rows) allRows.add(screen[r])
        if (allRows.isEmpty()) return emptyList()
        val rowCount = windowRows.coerceAtLeast(1)
        val maxOffset = (allRows.size - rowCount).coerceAtLeast(0)
        val offset = scrollbackOffsetRows.coerceIn(0, maxOffset)
        val start = (allRows.size - rowCount - offset).coerceAtLeast(0)
        val end = (start + rowCount).coerceAtMost(allRows.size)
        return allRows.subList(start, end)
    }

    private fun cellAt(row: Array<Cell>, col: Int): Cell {
        if (col in row.indices) return row[col]
        return EMPTY_CELL
    }

    companion object {
        private val EMPTY_CELL = Cell()

        fun makeScreen(rows: Int, cols: Int): Array<Array<Cell>> {
            return Array(rows) { Array(cols) { Cell() } }
        }

        fun clearScreenCells(screen: Array<Array<Cell>>) {
            for (row in screen) for (cell in row) cell.reset()
        }

        fun resizeScreen(old: Array<Array<Cell>>, oldRows: Int, oldCols: Int, newRows: Int, newCols: Int): Array<Array<Cell>> {
            val newScreen = makeScreen(newRows, newCols)
            val copyRows = minOf(oldRows, newRows)
            val copyCols = minOf(oldCols, newCols)
            for (r in 0 until copyRows) for (c in 0 until copyCols) newScreen[r][c].copyFrom(old[r][c])
            return newScreen
        }

        fun ansiColor(index: Int): Color {
            return when (index) {
                0 -> Color(0xFF2E3436); 1 -> Color(0xFFCC0000); 2 -> Color(0xFF4E9A06); 3 -> Color(0xFFC4A000)
                4 -> Color(0xFF3465A4); 5 -> Color(0xFF75507B); 6 -> Color(0xFF06989A); 7 -> Color(0xFFD3D7CF)
                8 -> Color(0xFF555753); 9 -> Color(0xFFEF2929); 10 -> Color(0xFF8AE234); 11 -> Color(0xFFFCE94F)
                12 -> Color(0xFF729FCF); 13 -> Color(0xFFAD7FA8); 14 -> Color(0xFF34E2E2); 15 -> Color(0xFFEEEEEC)
                else -> Color.Unspecified
            }
        }

        fun color256(n: Int): Color {
            return when {
                n < 16 -> ansiColor(n)
                n < 232 -> {
                    val idx = n - 16; val b = idx % 6; val g = (idx / 6) % 6; val r = idx / 36
                    val ri = if (r == 0) 0 else 55 + r * 40
                    val gi = if (g == 0) 0 else 55 + g * 40
                    val bi = if (b == 0) 0 else 55 + b * 40
                    Color(ri, gi, bi)
                }
                n < 256 -> { val v = 8 + (n - 232) * 10; Color(v, v, v) }
                else -> Color.Unspecified
            }
        }
    }
}

-- Keep table data intact while styling the LaTeX output consistently.
function Table(t)
  local weights, sum = {}, 0
  for i, spec in ipairs(t.colspecs) do
    local lengths, longest = {}, 0
    for _, body in ipairs(t.bodies) do
      for _, row in ipairs(body.body) do
        local cell = row.cells[i]
        if cell then
          local value = pandoc.utils.stringify(cell.contents)
          table.insert(lengths, utf8.len(value))
          for word in value:gmatch('%S+') do
            longest = math.max(longest, utf8.len(word))
          end
        end
      end
    end
    local average = 0
    for _, length in ipairs(lengths) do average = average + length end
    average = average / math.max(1, #lengths)
    local header = ''
    if t.head.rows[1] and t.head.rows[1].cells[i] then
      header = pandoc.utils.stringify(t.head.rows[1].cells[i].contents)
    end
    weights[i] = math.max(7, math.min(36, average + longest * 0.3),
                          math.min(18, utf8.len(header) * 0.65))
    sum = sum + weights[i]
    if i > 1 then
      local total, numeric = 0, 0
      for _, body in ipairs(t.bodies) do
        for _, row in ipairs(body.body) do
          local cell = row.cells[i]
          if cell then
            local value = pandoc.utils.stringify(cell.contents)
            total = total + 1
            if value:match('^%s*[−%-]?%d') and not value:match('^%d+/%d') then
              numeric = numeric + 1
            end
          end
        end
      end
      if total > 0 and numeric / total >= 0.75 then
        t.colspecs[i] = {pandoc.AlignRight, spec[2]}
      end
    end
  end
  -- Give even short numerical tables the full report width.
  for i, spec in ipairs(t.colspecs) do
    t.colspecs[i] = {spec[1], weights[i] / sum}
  end
  local latex = pandoc.write(pandoc.Pandoc({t}), 'latex')
  latex = latex:gsub('(\\toprule[^\n]*\n)', '%1\\rowcolor{ReportTint}\n')
  local rows = 0
  for _, body in ipairs(t.bodies) do rows = rows + #body.body end
  local sizing = rows >= 40 and '\\fontsize{9}{10.5}\\selectfont\n\\renewcommand{\\arraystretch}{1.0}\n'
                           or '\\fontsize{9.5}{12}\\selectfont\n\\renewcommand{\\arraystretch}{1.08}\n'
  return pandoc.RawBlock('latex', '\\begingroup\n' .. sizing .. latex .. '\n\\endgroup')
end

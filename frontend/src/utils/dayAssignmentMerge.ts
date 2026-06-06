type AttractionLike = {
  name: string
}

export function mergeDayAssignmentsWithSelected<T extends AttractionLike, U extends AttractionLike>(
  dayAssignments: U[][],
  selectedAttractions: T[],
): Array<Array<T & U>> {
  const selectedByName = new Map(selectedAttractions.map(attr => [attr.name, attr]))
  return dayAssignments.map(day =>
    day.map(attr => {
      const selected = selectedByName.get(attr.name)
      return selected ? ({ ...selected, ...attr } as T & U) : (attr as T & U)
    })
  )
}

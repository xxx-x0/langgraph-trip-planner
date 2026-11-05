type TravelGlobeLocation = {
  latitude: number
  longitude: number
}

export type TravelGlobeView = {
  phi: number
  theta: number
}

export function createFocusedGlobeView(
  location: TravelGlobeLocation,
): TravelGlobeView {
  return {
    phi: degreesToRadians(270 - location.longitude),
    theta: clamp(degreesToRadians(location.latitude), -0.85, 0.85),
  }
}

export function projectTravelGlobeLocation(
  location: TravelGlobeLocation,
  view: TravelGlobeView,
) {
  const [x, y, z] = toCobeVector(location)
  const cosTheta = Math.cos(view.theta)
  const sinTheta = Math.sin(view.theta)
  const cosPhi = Math.cos(view.phi)
  const sinPhi = Math.sin(view.phi)

  return {
    depth: -sinPhi * cosTheta * x + sinTheta * y + cosPhi * cosTheta * z,
    x: cosPhi * x + sinPhi * z,
    y: sinPhi * sinTheta * x + cosTheta * y - cosPhi * sinTheta * z,
  }
}

export function degreesToRadians(value: number) {
  return (value * Math.PI) / 180
}

export function easeNumber(current: number, target: number, amount: number) {
  return current + (target - current) * amount
}

export function easeAngle(current: number, target: number, amount: number) {
  return current + shortestAngleDelta(current, target) * amount
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function toCobeVector({ latitude, longitude }: TravelGlobeLocation) {
  const latitudeRadians = degreesToRadians(latitude)
  const longitudeRadians = degreesToRadians(longitude) - Math.PI
  const latitudeCosine = Math.cos(latitudeRadians)

  return [
    -latitudeCosine * Math.cos(longitudeRadians),
    Math.sin(latitudeRadians),
    latitudeCosine * Math.sin(longitudeRadians),
  ] as const
}

function shortestAngleDelta(current: number, target: number) {
  return Math.atan2(Math.sin(target - current), Math.cos(target - current))
}

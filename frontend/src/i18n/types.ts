export type AppLanguage = 'en' | 'de' | 'tr'

export const APP_LANGUAGES: readonly AppLanguage[] = ['en', 'de', 'tr']

export interface Dictionary {
  header: {
    weather: string
    profile: string
    openProfile: string
    workspace: string
    signIn: string
    signOut: string
    seniorMode: string
    companion: string
    language: string
    home: string
    travel: string
    menu: string
    closeMenu: string
  }
  weather: {
    airTemperature: string
    feelsLike: string
    wind: string
    rain: string
    uv: string
    air: string
    calibrated: (degrees: string) => string
    calibratedSenior: (degrees: string) => string
    checking: (place: string) => string
    unavailable: string
    tryAgain: string
    dismiss: string
    currentLocation: string
    locating: string
    searchCity: string
    morning: string
    afternoon: string
    evening: string
  }
  recommendation: {
    get: string
    preparing: string
    askNiva: string
    askNivaVoice: string
    listening: string
    stopListening: string
    askThinking: string
    voiceUnsupported: string
    micDenied: string
    speechMissed: string
    offline: string
    audioOn: string
    audioOff: string
    todaysOutfit: string
    requestOutfit: string
  }
  layers: {
    notNeeded: string
    base: string
    mid: string
    outer: string
    top: string
    bottom: string
    outerwear: string
    accessories: string
    todaysOutfit: string
  }
  garments: Record<string, string>
  feedback: {
    question: string
    tooCold: string
    perfect: string
    tooWarm: string
    sending: string
    toast: string
    signInPrompt: string
    signIn: string
    needsRecommendation: string
  }
  profile: {
    title: string
    intro: string
    back: string
    signInTitle: string
    signInBody: string
    signIn: string
    loading: string
    personal: string
    firstName: string
    lastName: string
    email: string
    phone: string
    optional: string
    savePersonal: string
    personalSaved: string
    security: string
    currentPassword: string
    newPassword: string
    confirmPassword: string
    changePassword: string
    passwordUpdated: string
    passwordShort: string
    passwordMismatch: string
    thermal: string
    activeDeviation: string
    baseline: (degrees: string) => string
    resetCalibration: string
    calibrationReset: string
    sensitivity: string
    coldEasily: string
    balanced: string
    warmEasily: string
    baselineCold: string
    baselineZero: string
    baselineWarm: string
    routine: string
    indoors: string
    outdoors: string
    gender: string
    men: string
    women: string
    other: string
    birthYear: string
    birthYearInvalid: (min: number, max: number) => string
    saveThermal: string
    thermalSaved: string
    preferredLanguage: string
    languageSaved: string
    tabSettings: string
    tabWardrobe: string
    wardrobeEmpty: string
    wardrobeLoading: string
    wardrobeAdd: string
    itemName: string
    itemNamePlaceholder: string
    imageUrl: string
    imageUrlPlaceholder: string
    category: string
    thickness: string
    style: string
    color: string
    waterproof: string
    addItem: string
    addingItem: string
    itemAdded: string
    updateItem: string
    updatingItem: string
    itemUpdated: string
    editItem: string
    cancelEdit: string
    wardrobeEdit: string
    columnName: string
    columnCategory: string
    columnDetails: string
    columnStatus: string
    columnActions: string
    deleteItem: string
    itemDeleted: string
    activeItem: string
    laundryItem: string
    categoryLabels: {
      'T-Shirt': string
      Sweater: string
      Pants: string
      Outerwear: string
      Shorts: string
      Accessory: string
    }
    thicknessLabels: {
      Thin: string
      Normal: string
      Thick: string
      Thermal: string
    }
    styleLabels: {
      Casual: string
      Sport: string
      Formal: string
      Outdoor: string
    }
    colorLabels: {
      Black: string
      Blue: string
      Red: string
      White: string
      Green: string
      Navy: string
      Grey: string
    }
  }
  workspace: {
    nav: string
    dashboard: string
    users: string
    trends: string
    back: string
    welcome: (name: string) => string
    dateRange: string
    today: string
    last7: string
    last30: string
    custom: string
    start: string
    end: string
    rangeInvalid: string
    city: string
    allCities: string
    gender: string
    allGenders: string
    men: string
    women: string
    other: string
    unspecified: string
    demographics: string
    demographicsCaption: string
    fetch: string
    signedInMember: string
    guestName: string
    retry: string
    refreshStatus: (count: number, range: string, place: string) => string
    overview: {
      loading: string
      loadError: string
      registeredUsers: string
      activeWearers: string
      totalRecommendations: string
      satisfaction: string
      activityTitle: string
      activityCaption: string
      activityChart: string
      count: string
      day: string
      recommendations: string
      feedback: string
      dayTip: (day: string, recommendations: number, feedback: number) => string
      sentimentTitle: string
      sentimentCaption: string
      sentimentChart: (percent: string) => string
      perfect: string
      tooCold: string
      tooWarm: string
      shareTip: (label: string, count: number, percentage: string) => string
      layersTitle: string
      layersCaption: string
      layersChart: string
      outfits: string
      noBands: string
      winterCoat: string
      lightJacket: string
      fleece: string
      tShirt: string
      accessoriesTitle: string
      accessoriesCaption: string
      noAccessories: string
      warmHat: string
      scarf: string
      gloves: string
      sunglasses: string
    }
    accounts: {
      searchLabel: string
      search: string
      loading: string
      loadError: string
      caption: string
      name: string
      email: string
      phone: string
      role: string
      roleUser: string
      rolePartner: string
      roleAdmin: string
      lastIp: string
      status: string
      actions: string
      active: string
      inactive: string
      editRole: string
      resetPassword: string
      deactivate: string
      activate: string
      previous: string
      next: string
      page: (current: number, total: number) => string
      empty: string
      roleUpdated: (name: string) => string
      nowInactive: (name: string) => string
      activeAgain: (name: string) => string
      resetTitle: string
      resetBody: (name: string) => string
      newPassword: string
      confirmPassword: string
      passwordShort: string
      passwordMismatch: string
      passwordSaved: (name: string) => string
      cancel: string
      savePassword: string
    }
    retail: {
      title: string
      summary: (city: string) => string
      everyCity: string
      category: string
      band: string
      all: string
      city: string
      temperature: string
      garment: string
      count: string
      share: string
      exportCsv: string
      loading: string
      loadError: string
      exportRange: string
      downloaded: string
      empty: string
      noMatch: string
      caption: string
      below5: string
      cool: string
      mild: string
      warm: string
      base: string
      mid: string
      outer: string
      accessory: string
    }
    storage: {
      title: string
      intro: string
      boundary: string
      older30: string
      older60: string
      older90: string
      custom: string
      start: string
      end: string
      rangeInvalid: string
      exportPurge: string
      purged: string
      loadError: string
      cancelled: string
      confirmTitle: string
      confirmEmpty: string
      confirmBody: (total: number, recommendations: number, feedback: number) => string
      backupReady: string
      close: string
      cancel: string
      purge: string
    }
  }
  forecast: {
    title: string
    high: string
    low: string
    rainChance: (percent: number) => string
    loading: string
    unavailable: string
    weekdays: {
      sunday: string
      monday: string
      tuesday: string
      wednesday: string
      thursday: string
      friday: string
      saturday: string
    }
  }
  travel: {
    title: string
    destination: string
    destinationPlaceholder: string
    start: string
    end: string
    plan: string
    planning: string
    checklist: string
    summary: string
    outlook: string
    wind: (speed: string) => string
    months: {
      january: string
      february: string
      march: string
      april: string
      may: string
      june: string
      july: string
      august: string
      september: string
      october: string
      november: string
      december: string
    }
    weekdaysShort: {
      sunday: string
      monday: string
      tuesday: string
      wednesday: string
      thursday: string
      friday: string
      saturday: string
    }
    base: string
    mid: string
    outer: string
    accessories: string
    rangeInvalid: string
    tooLong: string
    past: string
    chooseCity: string
    saveTrip: string
    savingTrip: string
    tripSaved: string
    myTrips: string
    noTrips: string
    shareWhatsapp: string
    copyChecklist: string
    copied: string
    deleteTrip: string
    tripDeleted: string
    tripTitle: (city: string) => string
    signInTitle: string
    signInBody: string
    login: string
    register: string
    notNow: string
    items: {
      base_shirt: string
      fleece: string
      light_jacket: string
      winter_coat: string
      waterproof_shell: string
      umbrella: string
      sunglasses: string
    }
  }
  common: {
    tryAgain: string
  }
}

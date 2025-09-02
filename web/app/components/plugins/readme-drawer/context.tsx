'use client'
import React, { createContext, useContext, useState } from 'react'
import type { FC, ReactNode } from 'react'
import type { PluginDetail } from '@/app/components/plugins/types'
import ReadmeDrawer from './index'

type ReadmeDrawerContextValue = {
  openReadme: (detail: PluginDetail, showType?: ShowType) => void
  closeReadme: () => void
  // isOpen: boolean
  currentDetailInfo?: {
    detail: PluginDetail
    showType: ShowType
  }
}

const ReadmeDrawerContext = createContext<ReadmeDrawerContextValue | null>(null)

export const useReadmeDrawer = (): ReadmeDrawerContextValue => {
  const context = useContext(ReadmeDrawerContext)
  if (!context)
    throw new Error('useReadmeDrawer must be used within ReadmeDrawerProvider')

  return context
}

type ReadmeDrawerProviderProps = {
  children: ReactNode
}

enum ShowType {
  drawer = 'drawer',
  modal = 'modal',
}

export const ReadmeDrawerProvider: FC<ReadmeDrawerProviderProps> = ({ children }) => {
  const [currentDetailInfo, setCurrentDetailInfo] = useState<{
    detail: PluginDetail
    showType: ShowType
  } | undefined>()

  const openReadme = (detail: PluginDetail, showType?: ShowType) => {
    setCurrentDetailInfo({
      detail,
      showType: showType || ShowType.drawer,
    })
  }

  const closeReadme = () => {
    setCurrentDetailInfo(undefined)
  }

  // todo: use zustand
  return (
    <ReadmeDrawerContext.Provider value={{
      openReadme,
      closeReadme,
      // isOpen: !!currentDetailInfo,
      currentDetailInfo,
    }}>
      {children}
      <ReadmeDrawer />
    </ReadmeDrawerContext.Provider>
  )
}

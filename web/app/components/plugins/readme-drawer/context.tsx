'use client'
import React, { createContext, useContext, useState } from 'react'
import type { FC, ReactNode } from 'react'
import type { PluginDetail } from '@/app/components/plugins/types'
import ReadmeDrawer from './index'

type ReadmeDrawerContextValue = {
  openReadme: (detail: PluginDetail) => void
  closeReadme: () => void
  isOpen: boolean
  currentDetail?: PluginDetail
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

export const ReadmeDrawerProvider: FC<ReadmeDrawerProviderProps> = ({ children }) => {
  const [currentDetail, setCurrentDetail] = useState<PluginDetail | undefined>()

  const openReadme = (detail: PluginDetail) => {
    setCurrentDetail(detail)
  }

  const closeReadme = () => {
    setCurrentDetail(undefined)
  }

  return (
    <ReadmeDrawerContext.Provider value={{
      openReadme,
      closeReadme,
      isOpen: !!currentDetail,
      currentDetail,
    }}>
      {children}
      <ReadmeDrawer detail={currentDetail} onClose={closeReadme} />
    </ReadmeDrawerContext.Provider>
  )
}

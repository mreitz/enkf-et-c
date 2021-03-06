#pull in data, define constants and model
import numpy as np
import os
import matplotlib.pyplot as mpl

savepath=os.path.dirname(os.path.abspath(__file__)) 

#MODIS satellite data
#Temperature
data=np.load(savepath+'\\MODIS_temp_et2.npz')
temp=data['alltemp']  #land surface temperature in degrees C. One daytime and one nighttime per 8 days. Mmt is in the middle of an 8-day stretch, representing its average.
temptimes=data['allttimes'] #julian day and fraction for the time of measurement. already adjusted to be in the middle of the 8 days.
tempqc=data['allqc'] #error bounds in K. values of 6 represent ">=3K" error from MODIS data. Lot of NaN values.

#PET and ET
#Units for the below: ET and PET data are totals over the 8 days following the julian date. In mm/8day.
#  QC is quality control, says non-cloudy for all but one point here. 
modisetall=data['etdata']
modiset=modisetall[0]
modispet=modisetall[1]
modisetqc=modisetall[2]
modetdays=data['days']  #these are the julian days for modis ET
modetdays+=4 #adjust the observations to halfway within the 8 day window

# flux tower ET data
#rows: timestamp in julian day with fraction, ET (mm/day), TA (air temp in C), PA (atmospheric pressure in kPa), NETRAD (net radiation in W/m^2)
data2=np.load(savepath+'\\fluxtower_et.npz')
fluxdata=data2['fluxdata']

#constants in model
c=0.993 #dimless correction factor
C_p=1.013 # kJ/kg/degC
r_ah=110 # s/m, calibrated in Senay paper
k=1.3 #correction factor scaling ref ET to rougher croups

def ssebop(Ts,refET,Ta,Pa,Rn):     
    airdensity=3.451*Pa/(Ta+273)
    Tc=c*Ta
    Th=Tc+Rn*r_ah/(airdensity*C_p)
    ET=(Th-Ts)*k*refET/(Th-Tc)
    return(ET)


# Parameters
N = 100 # number of ensemble members
n = 1 # size of the model state vector. Is this just 1 for ET, or multiple for ET, Temp, etc?
d0 = fluxdata[1] #array of observations through time. here starting with flux tower ET data in mm/day
sigma_d0=0.25*np.mean(d0) # ?  describe unknown mmt error distribution... wrote here 25% of mean
M=np.ones((len([d0[0]]),n)) # the measurement operator that maps the model state to the measurements d. If ET is both modeled and measured, ones.

ens_evol=np.ndarray((n,N,len(fluxdata[1]))) # to track the ensemble through time.

#Initialize ensemble based on first data point.
d=d0[0]+sigma_d0*np.random.randn(N)
ens_evol[0,:,0]=d #for multiple modeled variables, need to initialize them all

def find_nearest(array,value):
    idx = (np.abs(array-value)).argmin()
    return idx
    
for i in range(len(fluxdata[1])-1):
    d0 = [fluxdata[1][i+1]] #array of observations this timestep. here starting with just flux tower ET data in mm/day

    #Forecast step (using model to predict next timestep)
    state=ens_evol[0,:,i]
    A=np.ndarray((n,N))  #rows of the variables, columns of the ensemble members
    for j in range(len(state)):
        #surface temperature and refET... are at different timesteps. for now just find the closest one to this timestep ?   
        Tsurf=temp[find_nearest(temptimes,fluxdata[0][i+1])]
        refET=modispet[find_nearest(modetdays,fluxdata[0][i+1])]
        prediction=ssebop(Ts=Tsurf,refET=refET/8, Ta=fluxdata[2][i+1],Pa=fluxdata[3][i+1],Rn=fluxdata[4][i+1])        
        A[:,j]=prediction
    
    #Analysis step (incorporating mmt to get posterior distribution)
    # following Eqs 49-63 in Evenson 2009
    # Ensemble representation of the covariance
    Abar=np.dot(A,np.identity(N)/N)   # ensemble mean stored in each column of Abar
    Aprime=A-Abar    # ensemble perturbation matrix
    Cens=1./(N-1)*np.dot(Aprime,np.transpose(Aprime))  # ensemble covariance matrix
    
    # Measurement perturbations
    D=np.ndarray(shape=(len(d0),N)) #N vectors of perturbed observations
    E=np.ndarray(shape=(len(d0),N)) #ensemble of perturbations
    for j in range(N):    
        eps=sigma_d0*np.random.randn(len(d0))
        D[:,j]=d0+eps   #measurements + perturbations
        E[:,j]=eps
    Cerr=1./(N-1)*np.dot(E,np.transpose(E))   # error covariance matrix
    
    # Analysis equation
    #Aa=A+np.dot(np.dot(np.dot(Cens,np.transpose(M)),np.linalg.inv(np.dot(np.dot(M,Cens),np.transpose(M))+Cerr)),(d-np.dot(M,A))) # d in Eq 57 is if you do one ensemble member at a time
    #alternatively,
    Dprime=D-np.dot(M,A)
    S=np.dot(M,Aprime)
    C=np.dot(S,np.transpose(S))+ (N-1)*Cerr # Cerr note: either exact full-rank covar matrix or low-rank (ensemble) matrix
    X=np.identity(N)/N + np.dot(np.dot(np.transpose(S),np.linalg.inv(C)),Dprime)
    Aa=np.dot(A,X)

    ens_evol[:,:,i+1] = Aa

ens_mean=np.mean(ens_evol[:,:,:],axis=1)

mpl.figure() 
mpl.xlabel('Time in Julian days') 
mpl.ylabel('Filtered ET prediction, mm/day')
mpl.scatter(fluxdata[0],ens_mean)

